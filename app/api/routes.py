from html import escape
from json import dumps

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.api.security import (
    is_valid_admin_api_key,
    issue_admin_session_token,
    require_admin_api_key,
    require_admin_api_key_header_or_cookie,
    require_admin_api_key_query_or_cookie,
)
from app.core.taxonomies import DESIRED_FUTURES, PRIMARY_TOPICS, PRIMARY_TOPIC_LABELS_ES, TENSION_TYPES
from app.db.session import get_db
from app.schemas.common import HealthResponse
from app.schemas.admin_places import (
    PlaceCreateRequest,
    PlaceResponse,
    SegmentCreateRequest,
    SegmentImportResponse,
    SegmentResponse,
)
from app.schemas.admin_metrics import (
    ConversationMetricsResponse,
    PipelineMetricsResponse,
    ReviewMessageListResponse,
)
from app.schemas.conversation import EntryResponse, ThreadResponse, ThreadTurnResponse
from app.schemas.map import GridResponse, HeatmapResponse, MapPointsResponse, TimelapseResponse
from app.schemas.sentiment_audit import (
    SentimentAuditEvaluateRequest,
    SentimentAuditEvaluateResponse,
    SentimentAuditSampleResponse,
)
from app.schemas.taxonomy import (
    TaxonomyCandidateDecisionRequest,
    TaxonomyCandidateDecisionResponse,
    TaxonomyCandidateListResponse,
)
from app.schemas.feedback import FeedbackPatchRequest, FeedbackPatchResponse, FeedbackViewResponse
from app.schemas.ingest import IngestRequest, IngestResponse
from app.schemas.integrations import WhatsAppWebhookResponse
from app.schemas.jobs import ClusterJobRequest, ClusterJobResponse
from app.services.cluster_service import run_clustering_job
from app.services.feedback_service import get_feedback_view, patch_feedback
from app.services.ingest_service import ingest_message
from app.services.admin_metrics_service import (
    get_conversation_metrics,
    get_pipeline_metrics,
    get_review_messages,
    review_messages_to_csv,
)
from app.services.conversation_admin_service import list_place_entries, list_place_threads, list_thread_turns
from app.services.map_service import get_place_heatmap, get_place_map_points, get_place_sentiment_grid, get_place_timelapse
from app.services.place_admin_service import (
    create_place,
    create_segment,
    list_places,
    list_segments,
    replace_segments_from_csv,
)
from app.services.whatsapp_service import (
    process_meta_whatsapp_webhook,
    process_twilio_whatsapp_webhook,
    process_whatsapp_message,
    verify_meta_webhook,
)
from app.services.taxonomy_service import decide_taxonomy_candidate, list_taxonomy_candidates
from app.services.sentiment_audit_service import evaluate_sentiment_audit, get_sentiment_audit_sample

router = APIRouter()
admin_router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin_api_key_header_or_cookie)])

TOPIC_LABELS_ES = PRIMARY_TOPIC_LABELS_ES

FUTURE_LABELS_ES = {
    "more_shade": "Mas sombra",
    "cleaner_space": "Espacio mas limpio",
    "safer_nights": "Noches mas seguras",
    "better_crossings": "Mejores cruces",
    "more_cultural_activity": "Mas actividad cultural",
    "better_accessibility": "Mejor accesibilidad",
    "preserve_what_works": "Cuidar lo que ya funciona",
    "scale_positive_use": "Ampliar usos positivos",
    "other": "Otro",
}

TENSION_LABELS_ES = {
    "order_vs_expression": "Orden vs expresion",
    "flow_vs_stay": "Flujo vs permanencia",
    "commerce_vs_common_use": "Comercio vs uso comun",
    "security_vs_privacy": "Seguridad vs privacidad",
    "calm_vs_vitality": "Calma vs vitalidad",
    "preservation_vs_change": "Conservacion vs cambio",
    "none": "Sin tension",
    "other": "Otra",
}

FUTURE_VALENCE_HINT = {
    "safer_nights": "negative",
    "cleaner_space": "negative",
    "better_crossings": "negative",
    "more_shade": "neutral",
    "more_cultural_activity": "positive",
    "better_accessibility": "neutral",
    "preserve_what_works": "positive",
    "scale_positive_use": "positive",
    "other": "all",
}

TENSION_VALENCE_HINT = {
    "security_vs_privacy": "negative",
    "order_vs_expression": "negative",
    "flow_vs_stay": "neutral",
    "commerce_vs_common_use": "neutral",
    "calm_vs_vitality": "positive",
    "preservation_vs_change": "positive",
    "none": "positive",
    "other": "all",
}


def _render_feedback_edit_page(token: str, view: FeedbackViewResponse) -> str:
    original = view.transcript_text or view.original_text or ""
    options_topics = "".join(
        f"<option value=\"{escape(item)}\" {'selected' if item == view.primary_topic else ''}>{escape(TOPIC_LABELS_ES.get(item, item))}</option>"
        for item in PRIMARY_TOPICS
    )
    options_futures = "".join(
        f"<option data-valence=\"{escape(FUTURE_VALENCE_HINT.get(item, 'all'))}\" value=\"{escape(item)}\" {'selected' if item == view.desired_future else ''}>{escape(FUTURE_LABELS_ES.get(item, item))}</option>"
        for item in DESIRED_FUTURES
    )
    options_tensions = "".join(
        f"<option data-valence=\"{escape(TENSION_VALENCE_HINT.get(item, 'all'))}\" value=\"{escape(item)}\" {'selected' if item == view.tension_type else ''}>{escape(TENSION_LABELS_ES.get(item, item))}</option>"
        for item in TENSION_TYPES
    )
    token_js = dumps(token)

    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Agora - Revisar representacion</title>
  <style>
    :root {{
      --bg: #f4f2eb;
      --ink: #1f2a2e;
      --muted: #55686f;
      --line: #cfd7da;
      --panel: #ffffff;
      --accent: #0f766e;
      --accent-ink: #ffffff;
      --ok: #14532d;
      --ok-bg: #dcfce7;
      --err: #7f1d1d;
      --err-bg: #fee2e2;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: radial-gradient(circle at top, #f7f5ef, var(--bg));
      color: var(--ink);
      font-family: "Source Sans 3", "Segoe UI", sans-serif;
      line-height: 1.4;
    }}
    main {{
      max-width: 760px;
      margin: 24px auto;
      padding: 0 16px;
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 18px;
      box-shadow: 0 8px 24px rgba(31, 42, 46, 0.05);
    }}
    h1 {{ margin: 0 0 8px; font-size: 1.35rem; }}
    p {{ margin: 0 0 14px; color: var(--muted); }}
    .meta {{ color: var(--muted); font-size: 0.92rem; margin-bottom: 14px; }}
    label {{ display: block; font-weight: 650; margin: 12px 0 6px; }}
    input, textarea, select {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 10px;
      font: inherit;
      color: inherit;
      background: #fff;
    }}
    textarea {{ min-height: 88px; resize: vertical; }}
    .readonly {{ background: #f8f9fa; color: #44555b; }}
    .grid {{
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(1, minmax(0, 1fr));
    }}
    @media (min-width: 680px) {{
      .grid {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
    }}
    .check {{
      display: flex;
      gap: 8px;
      align-items: center;
      margin: 14px 0 4px;
      font-weight: 600;
    }}
    .check input {{ width: auto; }}
    button {{
      border: 0;
      border-radius: 10px;
      padding: 11px 14px;
      background: var(--accent);
      color: var(--accent-ink);
      font: inherit;
      font-weight: 700;
      cursor: pointer;
      margin-top: 8px;
    }}
    button[disabled] {{ opacity: .65; cursor: wait; }}
    .status {{
      margin-top: 12px;
      padding: 10px;
      border-radius: 10px;
      font-size: .95rem;
      display: none;
    }}
    .actions {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 8px;
    }}
    .secondary-btn {{
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 11px 14px;
      background: #fff;
      color: var(--ink);
      font: inherit;
      font-weight: 700;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      justify-content: center;
    }}
    .ok {{ display: block; background: var(--ok-bg); color: var(--ok); }}
    .err {{ display: block; background: var(--err-bg); color: var(--err); }}
  </style>
</head>
<body>
  <main>
    <div class="card">
      <h1>Revisar representacion de tu mensaje</h1>
      <p>Puedes ajustar como Agora lo entendio. El mensaje original no se borra.</p>
      <div class="meta">ID {escape(view.message_id)} - Version actual: <span id="version">{view.latest_version}</span></div>

      <label for="original_text">Mensaje original o transcripcion</label>
      <textarea id="original_text" class="readonly" readonly>{escape(original)}</textarea>

      <label for="summary_line">Como deberia quedar resumido</label>
      <textarea id="summary_line">{escape(view.summary_line)}</textarea>

      <label for="place_reference">Nombre o referencia del lugar</label>
      <input id="place_reference" type="text" value="{escape(view.place_reference or '')}" placeholder="Ej: Esquina norte junto al paradero" />

      <div class="grid">
        <div>
          <label for="primary_topic">Tema principal</label>
          <select id="primary_topic">{options_topics}</select>
        </div>
        <div>
          <label for="desired_future">Futuro deseado</label>
          <select id="desired_future">{options_futures}</select>
        </div>
        <div>
          <label for="tension_type">Tension</label>
          <select id="tension_type">{options_tensions}</select>
        </div>
      </div>

      <label for="quote_snippet">Cita breve (literal)</label>
      <textarea id="quote_snippet">{escape(view.quote_snippet)}</textarea>

      <label for="clarification_note">Aclaracion adicional (opcional)</label>
      <textarea id="clarification_note" placeholder="Puedes explicar o reescribir mejor lo que quisiste decir.">{escape(view.clarification_note or "")}</textarea>

      <label class="check"><input id="allow_public_quote" type="checkbox" {"checked" if view.allow_public_quote else ""} />Permitir cita publica literal</label>

      <div class="actions">
        <button id="save_btn" type="button">Guardar correcciones</button>
        <a id="back_to_whatsapp" class="secondary-btn" href="https://wa.me/" target="_blank" rel="noopener noreferrer">Volver a WhatsApp</a>
      </div>
      <div id="status" class="status"></div>
    </div>
  </main>
  <script>
    const token = {token_js};
    const saveBtn = document.getElementById("save_btn");
    const statusBox = document.getElementById("status");
    const version = document.getElementById("version");
    function showStatus(message, ok) {{
      statusBox.className = "status " + (ok ? "ok" : "err");
      statusBox.textContent = message;
    }}
    function inferValence() {{
      const txt = (document.getElementById("summary_line").value + " " + document.getElementById("quote_snippet").value).toLowerCase();
      const positive = ["me gusta","bonito","tranquilo","limpio","agradable","mejor","verde","seguro","funciona bien"];
      const negative = ["miedo","insegur","basura","sucio","ruido","peligro","oscuro","robo","falta","horrible","pesimo"];
      const pos = positive.filter((w) => txt.includes(w)).length;
      const neg = negative.filter((w) => txt.includes(w)).length;
      if (pos > neg) return "positive";
      if (neg > pos) return "negative";
      return "neutral";
    }}
    function filterOptionsByValence(selectId) {{
      const valence = inferValence();
      const sel = document.getElementById(selectId);
      const current = sel.value;
      let stillVisible = false;
      for (const opt of Array.from(sel.options)) {{
        const hint = opt.dataset.valence || "all";
        const visible = hint === "all" || hint === "neutral" || hint === valence;
        opt.hidden = !visible;
        if (visible && opt.value === current) stillVisible = true;
      }}
      if (!stillVisible) {{
        const firstVisible = Array.from(sel.options).find((o) => !o.hidden);
        if (firstVisible) sel.value = firstVisible.value;
      }}
    }}
    function refreshValenceDrivenOptions() {{
      filterOptionsByValence("desired_future");
      filterOptionsByValence("tension_type");
    }}
    function humanizeValidation(detail) {{
      if (!Array.isArray(detail)) {{
        return "Revisa los campos y vuelve a intentar.";
      }}
      const fieldLabels = {{
        summary_line: "Resumen",
        primary_topic: "Tema principal",
        desired_future: "Futuro deseado",
        tension_type: "Tension",
        quote_snippet: "Cita breve",
        clarification_note: "Aclaracion",
        place_reference: "Referencia del lugar"
      }};
      const lines = detail.map((item) => {{
        const loc = Array.isArray(item.loc) ? item.loc : [];
        const field = loc.length ? String(loc[loc.length - 1]) : "";
        const label = fieldLabels[field] || "Campo";
        let msg = String(item.msg || "Valor invalido.");
        msg = msg.replace(/^Value error,\\s*/i, "");
        if (msg.startsWith("Input should")) {{
          msg = "valor invalido.";
        }}
        return `${{label}}: ${{msg}}`;
      }});
      return lines.join(" ");
    }}
    async function saveFeedback() {{
      saveBtn.disabled = true;
      statusBox.className = "status";
      const payload = {{
        summary_line: document.getElementById("summary_line").value.trim(),
        primary_topic: document.getElementById("primary_topic").value,
        desired_future: document.getElementById("desired_future").value,
        tension_type: document.getElementById("tension_type").value,
        quote_snippet: document.getElementById("quote_snippet").value.trim(),
        clarification_note: document.getElementById("clarification_note").value.trim() || null,
        place_reference: document.getElementById("place_reference").value.trim() || null,
        allow_public_quote: document.getElementById("allow_public_quote").checked
      }};
      try {{
        const res = await fetch(`/feedback/${{token}}`, {{
          method: "PATCH",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify(payload)
        }});
        const data = await res.json();
        if (!res.ok) {{
          const detail = (data && data.detail) ? data.detail : null;
          if (typeof detail === "string") {{
            throw new Error(detail);
          }}
          if (Array.isArray(detail)) {{
            throw new Error(humanizeValidation(detail));
          }}
          throw new Error("No se pudo guardar.");
        }}
        version.textContent = String(data.new_version);
        showStatus("Correccion guardada. Version " + data.new_version + " creada.", true);
      }} catch (err) {{
        showStatus("Error al guardar: " + err.message, false);
      }} finally {{
        saveBtn.disabled = false;
      }}
    }}
    saveBtn.addEventListener("click", saveFeedback);
    document.getElementById("back_to_whatsapp").addEventListener("click", (ev) => {{
      ev.preventDefault();
      window.location.href = "whatsapp://send";
      setTimeout(() => {{
        window.open("https://wa.me/", "_blank", "noopener,noreferrer");
      }}, 250);
    }});
    document.getElementById("summary_line").addEventListener("input", refreshValenceDrivenOptions);
    document.getElementById("quote_snippet").addEventListener("input", refreshValenceDrivenOptions);
    refreshValenceDrivenOptions();
  </script>
</body>
</html>"""


def _render_place_map_page(place_id: int, period_days: int, heatmap_mode: str) -> str:
    _ = heatmap_mode
    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Agora Map - Place {place_id}</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <style>
    body {{ margin: 0; font-family: "Source Sans 3", "Segoe UI", sans-serif; color: #1f2a2e; }}
    #topbar {{
      padding: 10px 14px;
      border-bottom: 1px solid #d3dbde;
      background: #f7f9f8;
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
    }}
    #map {{ width: 100vw; height: calc(100vh - 56px); }}
    select, button, input {{
      border: 1px solid #b8c7cc;
      border-radius: 8px;
      padding: 6px 10px;
      font: inherit;
      background: #fff;
    }}
    .stat {{ color: #46606a; font-size: 0.95rem; }}
  </style>
</head>
<body>
  <div id="topbar">
    <strong>Place {place_id}</strong>
    <label>Dias <input id="period_days" type="number" min="1" max="365" value="{period_days}" style="width:80px;" /></label>
    <label>Diametro
      <select id="grid_cell_m">
        <option value="50">50m</option>
        <option value="100" selected>100m</option>
        <option value="200">200m</option>
      </select>
    </label>
    <button id="reload">Recargar</button>
    <span id="stats" class="stat"></span>
  </div>
  <div id="map"></div>

  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    const placeId = {place_id};
    let gridLayer = null;
    const map = L.map('map').setView([-33.445, -70.66], 13);
    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors'
    }}).addTo(map);

    function gridColor(avgScore) {{
      const s = Math.max(-1, Math.min(1, Number(avgScore || 0)));
      if (s <= -0.6) return "#b91c1c";
      if (s <= -0.2) return "#ef4444";
      if (s < 0.2) return "#f59e0b";
      if (s < 0.6) return "#84cc16";
      return "#16a34a";
    }}

    function clearGrid() {{
      if (gridLayer) {{
        map.removeLayer(gridLayer);
        gridLayer = null;
      }}
    }}

    function renderGrid(gridData) {{
      clearGrid();
      const cells = Array.isArray(gridData.cells) ? gridData.cells : [];
      if (cells.length === 0) {{
        document.getElementById("stats").textContent = "Sin puntos geolocalizados para este periodo";
        return;
      }}
      const rects = cells.map((c) => {{
        const color = gridColor(c.avg_sentiment_score);
        const rect = L.rectangle(
          [[c.min_latitude, c.min_longitude], [c.max_latitude, c.max_longitude]],
          {{ color, weight: 1, fillColor: color, fillOpacity: 0.38 }}
        );
        rect.bindPopup(
          `Escala: ${{c.sentiment_scale_label_es}} (${{c.sentiment_scale_value}})<br/>` +
          `Promedio: ${{c.avg_sentiment_score}}<br/>` +
          `Mensajes: ${{c.message_count}}`
        );
        return rect;
      }});
      gridLayer = L.layerGroup(rects).addTo(map);
      const bounds = L.featureGroup(rects).getBounds();
      if (bounds.isValid()) {{
        map.fitBounds(bounds, {{ padding: [20, 20] }});
      }}
      document.getElementById("stats").textContent = `celdas=${{cells.length}} diametro=${{gridData.cell_meters}}m`;
    }}

    async function loadGrid() {{
      const periodDays = Number(document.getElementById("period_days").value || "30");
      const cellMeters = Number(document.getElementById("grid_cell_m").value || "100");
      const res = await fetch(`/admin/places/${{placeId}}/map/grid?period_days=${{periodDays}}&cell_m=${{cellMeters}}&limit=5000`);
      if (!res.ok) {{
        document.getElementById("stats").textContent = "Error cargando grilla (requiere login admin)";
        return;
      }}
      const data = await res.json();
      renderGrid(data);
    }}

    document.getElementById("reload").addEventListener("click", loadGrid);
    document.getElementById("grid_cell_m").addEventListener("change", loadGrid);
    loadGrid();
  </script>
</body>
</html>"""


def _render_admin_login_page(message: str | None = None) -> str:
    msg_html = f"<p style='color:#b91c1c'>{escape(message)}</p>" if message else ""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Agora Admin Login</title>
  <style>
    body {{ margin:0; background:#f3f6f7; font-family:"Source Sans 3","Segoe UI",sans-serif; color:#1f2a2e; }}
    main {{ min-height:100vh; display:grid; place-items:center; padding:20px; }}
    .card {{ width:100%; max-width:420px; background:#fff; border:1px solid #d0dadd; border-radius:12px; padding:18px; }}
    h1 {{ margin:0 0 10px; font-size:1.25rem; }}
    label {{ display:block; font-weight:600; margin:10px 0 6px; }}
    input {{ width:100%; border:1px solid #b9c8cd; border-radius:8px; padding:8px 10px; font:inherit; }}
    button {{ margin-top:14px; border:0; border-radius:8px; padding:10px 12px; background:#0f766e; color:#fff; font:inherit; font-weight:700; width:100%; cursor:pointer; }}
  </style>
</head>
<body>
  <main>
    <form class="card" method="post" action="/admin/session/login">
      <h1>Admin Session</h1>
      <p>Enter admin key to start a secure session cookie.</p>
      {msg_html}
      <label for="admin_api_key">Admin API key</label>
      <input id="admin_api_key" name="admin_api_key" type="password" required />
      <label for="place_id">Default place id</label>
      <input id="place_id" name="place_id" type="number" min="1" value="1" required />
      <button type="submit">Login</button>
    </form>
  </main>
</body>
</html>"""


def _clip(value: str | None, max_len: int = 120) -> str:
    if not value:
        return ""
    clean = value.replace("\n", " ").strip()
    if len(clean) <= max_len:
        return clean
    return clean[: max_len - 1] + "…"


def _render_admin_review_table_page(data: ReviewMessageListResponse, limit: int, offset: int) -> str:
    rows = []
    for item in data.items:
        rows.append(
            "<tr>"
            f"<td>{escape(item.created_at.isoformat())}</td>"
            "<td>planeta tierra</td>"
            f"<td>{item.latitude if item.latitude is not None else '-'}</td>"
            f"<td>{item.longitude if item.longitude is not None else '-'}</td>"
            f"<td>{escape(item.source_type)}</td>"
            f"<td>{escape(_clip(item.original_text, 120) or _clip(item.transcript_text, 120) or '-')}</td>"
            f"<td>{escape(TOPIC_LABELS_ES.get(item.final_primary_topic or '', item.final_primary_topic or '-'))}</td>"
            f"<td>{item.versions_count}</td>"
            f"<td>{'si' if item.corrected else 'no'}</td>"
            "</tr>"
        )

    body_rows = "\n".join(rows) if rows else "<tr><td colspan='9'>No hay mensajes aun.</td></tr>"
    prev_offset = max(0, offset - limit)
    next_offset = offset + limit
    has_next = next_offset < data.total

    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Agora Admin - Mensajes</title>
  <style>
    body {{ margin:0; background:#f3f6f7; font-family:"Source Sans 3","Segoe UI",sans-serif; color:#1f2a2e; }}
    main {{ max-width:1200px; margin:18px auto; padding:0 14px 20px; }}
    .card {{ background:#fff; border:1px solid #d0dadd; border-radius:12px; padding:14px; }}
    h1 {{ margin:0 0 8px; font-size:1.2rem; }}
    .meta {{ color:#48616a; font-size:.95rem; margin-bottom:10px; }}
    table {{ width:100%; border-collapse:collapse; font-size:.93rem; }}
    th, td {{ border:1px solid #d8e2e6; padding:8px; text-align:left; vertical-align:top; }}
    th {{ background:#eef4f6; font-weight:700; }}
    .controls {{ display:flex; gap:8px; align-items:center; margin-bottom:10px; flex-wrap:wrap; }}
    input[type=number] {{ border:1px solid #b9c8cd; border-radius:8px; padding:6px 8px; width:90px; }}
    button, a.btn {{ border:0; border-radius:8px; padding:7px 10px; background:#0f766e; color:#fff; text-decoration:none; font:inherit; font-weight:700; cursor:pointer; }}
    a.btn.secondary {{ background:#475a61; }}
  </style>
</head>
<body>
  <main>
    <div class="card">
      <h1>Mensajes del sistema</h1>
      <div class="meta">Total: {data.total} | Mostrando {len(data.items)} | Offset: {offset}</div>
      <form class="controls" method="get" action="/admin/messages/review/view">
        <label for="limit">Limit</label>
        <input id="limit" name="limit" type="number" min="1" max="500" value="{limit}" />
        <label for="offset">Offset</label>
        <input id="offset" name="offset" type="number" min="0" value="{offset}" />
        <button type="submit">Actualizar</button>
        <a class="btn secondary" href="/admin/messages/review.csv?limit={limit}&offset={offset}">Exportar CSV</a>
      </form>
      <table>
        <thead>
          <tr>
            <th>Fecha</th>
            <th>Lugar</th>
            <th>Latitud</th>
            <th>Longitud</th>
            <th>Tipo</th>
            <th>Mensaje</th>
            <th>Tema final</th>
            <th>Versiones</th>
            <th>Corregido</th>
          </tr>
        </thead>
        <tbody>
          {body_rows}
        </tbody>
      </table>
      <div class="controls" style="margin-top:10px">
        <a class="btn secondary" href="/admin/messages/review/view?limit={limit}&offset={prev_offset}">Anterior</a>
        <a class="btn {'secondary' if has_next else ''}" href="/admin/messages/review/view?limit={limit}&offset={next_offset}">Siguiente</a>
      </div>
    </div>
  </main>
</body>
</html>"""


def _render_admin_sentiment_audit_page(sample_size: int = 10) -> str:
    size = max(1, min(100, int(sample_size)))
    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Agora Admin - Auditoria Sentimiento</title>
  <style>
    body {{ margin:0; background:#f3f6f7; font-family:"Source Sans 3","Segoe UI",sans-serif; color:#1f2a2e; }}
    main {{ max-width:1200px; margin:18px auto; padding:0 14px 20px; }}
    .card {{ background:#fff; border:1px solid #d0dadd; border-radius:12px; padding:14px; margin-bottom:12px; }}
    h1 {{ margin:0 0 8px; font-size:1.2rem; }}
    .meta {{ color:#48616a; font-size:.95rem; margin-bottom:10px; }}
    table {{ width:100%; border-collapse:collapse; font-size:.92rem; }}
    th, td {{ border:1px solid #d8e2e6; padding:8px; text-align:left; vertical-align:top; }}
    th {{ background:#eef4f6; font-weight:700; }}
    select, button, input {{ border:1px solid #b9c8cd; border-radius:8px; padding:6px 8px; font:inherit; background:#fff; }}
    button {{ background:#0f766e; color:#fff; border:0; font-weight:700; cursor:pointer; }}
    .row {{ display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-bottom:10px; }}
    .result {{ font-weight:700; }}
  </style>
</head>
<body>
  <main>
    <div class="card">
      <h1>Chequeo Manual de Sentimiento</h1>
      <div class="meta">Selecciona muestra aleatoria, etiqueta manualmente y compara contra modelo y heuristica.</div>
      <div class="row">
        <label for="sample_size">Muestra</label>
        <input id="sample_size" type="number" min="1" max="100" value="{size}" />
        <label for="reviewer_tag">Tag admin</label>
        <input id="reviewer_tag" type="text" maxlength="64" placeholder="ej: demian" />
        <button id="load_sample">Cargar muestra</button>
        <button id="run_eval">Comparar</button>
      </div>
      <div id="result" class="result"></div>
    </div>

    <div class="card">
      <table>
        <thead>
          <tr>
            <th>Mensaje</th>
            <th>Manual</th>
            <th>Modelo</th>
            <th>Heuristica</th>
          </tr>
        </thead>
        <tbody id="rows">
          <tr><td colspan="4">Cargando...</td></tr>
        </tbody>
      </table>
    </div>
  </main>
  <script>
    let currentSample = [];

    function esc(s) {{
      return String(s || "").replace(/[&<>"]/g, (c) => ({{"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;"}}[c]));
    }}

    function manualSelect(id) {{
      return `
        <select data-message-id="${{id}}">
          <option value="negative">negativo</option>
          <option value="neutral" selected>neutral</option>
          <option value="positive">positivo</option>
        </select>
      `;
    }}

    function renderRows(items) {{
      const tbody = document.getElementById("rows");
      if (!Array.isArray(items) || items.length === 0) {{
        tbody.innerHTML = '<tr><td colspan="4">Sin datos.</td></tr>';
        return;
      }}
      tbody.innerHTML = items.map((it) => `
        <tr>
          <td>${{esc(it.text)}}</td>
          <td>${{manualSelect(it.message_id)}}</td>
          <td>${{esc(it.model_label)}}${{it.model_score !== null && it.model_score !== undefined ? ` (${{it.model_score}})` : ""}}</td>
          <td>${{esc(it.heuristic_label)}}</td>
        </tr>
      `).join("");
    }}

    async function loadSample() {{
      const n = Number(document.getElementById("sample_size").value || "10");
      const res = await fetch(`/admin/sentiment/audit/sample?sample_size=${{n}}`);
      if (!res.ok) {{
        document.getElementById("rows").innerHTML = '<tr><td colspan="4">Error al cargar muestra.</td></tr>';
        return;
      }}
      const data = await res.json();
      currentSample = data.items || [];
      renderRows(currentSample);
      document.getElementById("result").textContent = `Muestra cargada: ${{data.sample_size}} mensajes`;
    }}

    async function runEval() {{
      const selectors = Array.from(document.querySelectorAll("select[data-message-id]"));
      const items = selectors.map((sel) => ({{
        message_id: sel.getAttribute("data-message-id"),
        manual_label: sel.value
      }}));
      const reviewerTag = String(document.getElementById("reviewer_tag").value || "").trim();
      const res = await fetch("/admin/sentiment/audit/evaluate", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{ reviewer_tag: reviewerTag || null, items }})
      }});
      if (!res.ok) {{
        document.getElementById("result").textContent = "Error en comparacion.";
        return;
      }}
      const data = await res.json();
      document.getElementById("result").textContent =
        `Review: ${{data.review_id || "-"}} | Tag: ${{data.reviewer_tag || "-"}} | Comparados: ${{data.compared_count}} | Modelo: ${{data.model_accuracy_pct}}% | Heuristica: ${{data.heuristic_accuracy_pct}}%`;
    }}

    document.getElementById("load_sample").addEventListener("click", loadSample);
    document.getElementById("run_eval").addEventListener("click", runEval);
    loadSample();
  </script>
</body>
</html>"""


def _render_admin_home_page(place_id: int = 1) -> str:
    safe_place_id = max(1, int(place_id))
    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Agora Admin - Home</title>
  <style>
    body {{ margin:0; background:#f3f6f7; font-family:"Source Sans 3","Segoe UI",sans-serif; color:#1f2a2e; }}
    main {{ max-width:1100px; margin:18px auto; padding:0 14px 20px; }}
    .top {{ display:flex; gap:10px; align-items:center; justify-content:space-between; flex-wrap:wrap; margin-bottom:12px; }}
    h1 {{ margin:0; font-size:1.25rem; }}
    .sub {{ color:#48616a; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(250px,1fr)); gap:12px; }}
    .card {{ background:#fff; border:1px solid #d0dadd; border-radius:12px; padding:14px; }}
    .card h2 {{ margin:0 0 6px; font-size:1.02rem; }}
    .card p {{ margin:0 0 10px; color:#48616a; font-size:.95rem; }}
    a.btn, button {{ display:inline-block; border:0; border-radius:8px; padding:8px 10px; background:#0f766e; color:#fff; text-decoration:none; font:inherit; font-weight:700; cursor:pointer; margin:3px 4px 0 0; }}
    a.btn.secondary {{ background:#475a61; }}
    input[type=number] {{ border:1px solid #b9c8cd; border-radius:8px; padding:6px 8px; width:90px; }}
    form.inline {{ display:inline-flex; gap:8px; align-items:center; flex-wrap:wrap; }}
  </style>
</head>
<body>
  <main>
    <div class="top">
      <div>
        <h1>Admin Home</h1>
        <div class="sub">Elige la vista que quieres usar.</div>
      </div>
      <form class="inline" method="post" action="/admin/session/logout">
        <button type="submit" style="background:#6b1f1f">Cerrar sesion</button>
      </form>
    </div>

    <div class="card" style="margin-bottom:12px">
      <form class="inline" method="get" action="/admin/home">
        <label for="place_id">Place ID</label>
        <input id="place_id" name="place_id" type="number" min="1" value="{safe_place_id}" />
        <button type="submit">Actualizar</button>
      </form>
    </div>

    <div class="grid">
      <div class="card">
        <h2>Vistas Web</h2>
        <p>Pantallas listas para uso manual.</p>
        <a class="btn" href="/admin/places/{safe_place_id}/map/view">Mapa</a>
        <a class="btn" href="/admin/messages/review/view">Tabla de mensajes</a>
      </div>

      <div class="card">
        <h2>Metricas</h2>
        <p>Endpoints JSON para monitoreo rapido.</p>
        <a class="btn secondary" href="/admin/metrics/pipeline">Pipeline JSON</a>
        <a class="btn secondary" href="/admin/metrics/conversation">Conversacion JSON</a>
      </div>

      <div class="card">
        <h2>Revision y Export</h2>
        <p>Datos crudos de revision y descarga CSV.</p>
        <a class="btn secondary" href="/admin/messages/review?limit=100&offset=0">Review JSON</a>
        <a class="btn secondary" href="/admin/messages/review.csv?limit=1000&offset=0">Review CSV</a>
        <a class="btn secondary" href="/admin/sentiment/audit/view">Auditoria sentimiento</a>
        <a class="btn secondary" href="/admin/taxonomy/candidates?status=pending&limit=100">Taxonomia pendientes JSON</a>
      </div>

      <div class="card">
        <h2>Lugares</h2>
        <p>Gestion de lugares/segmentos via API.</p>
        <a class="btn secondary" href="/admin/places">Places JSON</a>
        <a class="btn secondary" href="/admin/places/{safe_place_id}/map/points?period_days=30&limit=3000">Map Points JSON</a>
      </div>
    </div>
  </main>
</body>
</html>"""


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.post("/ingest", response_model=IngestResponse)
def ingest(payload: IngestRequest, db: Session = Depends(get_db)) -> IngestResponse:
    return ingest_message(db, payload)


@router.get("/feedback/{token}", response_model=FeedbackViewResponse)
def feedback_view(token: str, db: Session = Depends(get_db)) -> FeedbackViewResponse:
    return get_feedback_view(db, token)


@router.get("/feedback/{token}/edit", response_class=HTMLResponse)
def feedback_edit_page(token: str, db: Session = Depends(get_db)) -> HTMLResponse:
    view = get_feedback_view(db, token)
    return HTMLResponse(content=_render_feedback_edit_page(token, view))


@router.patch("/feedback/{token}", response_model=FeedbackPatchResponse)
def feedback_patch(
    token: str,
    payload: FeedbackPatchRequest,
    db: Session = Depends(get_db),
) -> FeedbackPatchResponse:
    return patch_feedback(db, token, payload)


@router.get("/admin/session/login", response_class=HTMLResponse)
def admin_session_login_page(message: str | None = Query(default=None)) -> HTMLResponse:
    return HTMLResponse(content=_render_admin_login_page(message=message))


@router.get("/admin/home", response_class=HTMLResponse)
def admin_home(
    place_id: int = Query(default=1, ge=1),
    _: None = Depends(require_admin_api_key_query_or_cookie),
) -> HTMLResponse:
    return HTMLResponse(content=_render_admin_home_page(place_id=place_id))


@router.post("/admin/session/login")
def admin_session_login(
    admin_api_key: str = Form(...),
    place_id: int = Form(default=1),
) -> RedirectResponse:
    # Validate with the same dependency logic by comparing against configured key.
    # We do not echo details to avoid key probing.
    if not admin_api_key:
        return RedirectResponse(url="/admin/session/login?message=Missing+key", status_code=303)

    if not is_valid_admin_api_key(admin_api_key):
        return RedirectResponse(url="/admin/session/login?message=Invalid+key", status_code=303)

    response = RedirectResponse(url=f"/admin/home?place_id={place_id}", status_code=303)
    response.set_cookie(
        key="admin_session",
        value=issue_admin_session_token(),
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )
    return response


@router.post("/admin/session/logout")
def admin_session_logout() -> RedirectResponse:
    response = RedirectResponse(url="/admin/session/login?message=Session+closed", status_code=303)
    response.delete_cookie("admin_session", path="/")
    return response


@router.post("/integrations/whatsapp/webhook", response_model=WhatsAppWebhookResponse)
def whatsapp_webhook(
    Body: str | None = Form(default=None),
    Latitude: float | None = Form(default=None),
    Longitude: float | None = Form(default=None),
    Address: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> WhatsAppWebhookResponse:
    return process_whatsapp_message(
        db=db,
        body=Body,
        latitude=Latitude,
        longitude=Longitude,
        address=Address,
    )


@router.post("/integrations/whatsapp/twilio/webhook", response_model=WhatsAppWebhookResponse)
async def twilio_whatsapp_webhook(request: Request, db: Session = Depends(get_db)) -> WhatsAppWebhookResponse:
    form = await request.form()
    return process_twilio_whatsapp_webhook(
        db=db,
        url=str(request.url),
        form_data=dict(form.items()),
        twilio_signature=request.headers.get("X-Twilio-Signature"),
    )


@router.get("/integrations/whatsapp/meta/webhook", response_class=PlainTextResponse)
def meta_whatsapp_verify(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
) -> PlainTextResponse:
    challenge = verify_meta_webhook(
        mode=hub_mode,
        verify_token=hub_verify_token,
        challenge=hub_challenge,
    )
    return PlainTextResponse(content=challenge)


@router.post("/integrations/whatsapp/meta/webhook", response_model=WhatsAppWebhookResponse)
async def meta_whatsapp_webhook(request: Request, db: Session = Depends(get_db)) -> WhatsAppWebhookResponse:
    raw_body = await request.body()
    return process_meta_whatsapp_webhook(
        db=db,
        raw_body=raw_body,
        meta_signature=request.headers.get("X-Hub-Signature-256"),
    )


@admin_router.post("/jobs/cluster", response_model=ClusterJobResponse)
def run_cluster_job(payload: ClusterJobRequest, db: Session = Depends(get_db)) -> ClusterJobResponse:
    return run_clustering_job(
        db=db,
        similarity_threshold=payload.similarity_threshold,
        min_cluster_size=payload.min_cluster_size,
    )


@admin_router.post("/places", response_model=PlaceResponse)
def admin_create_place(payload: PlaceCreateRequest, db: Session = Depends(get_db)) -> PlaceResponse:
    return create_place(db, payload)


@admin_router.get("/places", response_model=list[PlaceResponse])
def admin_list_places(db: Session = Depends(get_db)) -> list[PlaceResponse]:
    return list_places(db)


@admin_router.post("/places/{place_code}/segments", response_model=SegmentResponse)
def admin_create_segment(
    place_code: str,
    payload: SegmentCreateRequest,
    db: Session = Depends(get_db),
) -> SegmentResponse:
    return create_segment(db, place_code, payload)


@admin_router.get("/places/{place_code}/segments", response_model=list[SegmentResponse])
def admin_list_segments(place_code: str, db: Session = Depends(get_db)) -> list[SegmentResponse]:
    return list_segments(db, place_code)


@admin_router.post("/places/{place_code}/segments/import", response_model=SegmentImportResponse)
async def admin_import_segments(
    place_code: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> SegmentImportResponse:
    content = await file.read()
    return replace_segments_from_csv(db, place_code, content)


@admin_router.get("/metrics/pipeline", response_model=PipelineMetricsResponse)
def admin_pipeline_metrics(
    period_days: int = Query(default=7, ge=1, le=365),
    db: Session = Depends(get_db),
) -> PipelineMetricsResponse:
    return get_pipeline_metrics(db, period_days=period_days)


@admin_router.get("/metrics/conversation", response_model=ConversationMetricsResponse)
def admin_conversation_metrics(
    period_days: int = Query(default=7, ge=1, le=365),
    db: Session = Depends(get_db),
) -> ConversationMetricsResponse:
    return get_conversation_metrics(db, period_days=period_days)


@admin_router.get("/messages/review", response_model=ReviewMessageListResponse)
def admin_review_messages(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> ReviewMessageListResponse:
    return get_review_messages(db, limit=limit, offset=offset)


@admin_router.get("/messages/review.csv")
def admin_review_messages_csv(
    limit: int = Query(default=1000, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> PlainTextResponse:
    data = get_review_messages(db, limit=limit, offset=offset)
    csv_content = review_messages_to_csv(data)
    headers = {"Content-Disposition": "attachment; filename=review_messages.csv"}
    return PlainTextResponse(content=csv_content, media_type="text/csv", headers=headers)


@admin_router.get("/taxonomy/candidates", response_model=TaxonomyCandidateListResponse)
def admin_list_taxonomy_candidates(
    status: str = Query(default="pending"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> TaxonomyCandidateListResponse:
    return list_taxonomy_candidates(db, status=status, limit=limit, offset=offset)


@admin_router.post("/taxonomy/candidates/{candidate_id}/approve", response_model=TaxonomyCandidateDecisionResponse)
def admin_approve_taxonomy_candidate(
    candidate_id: str,
    payload: TaxonomyCandidateDecisionRequest,
    db: Session = Depends(get_db),
) -> TaxonomyCandidateDecisionResponse:
    result = decide_taxonomy_candidate(db, candidate_id=candidate_id, status="approved", review_note=payload.review_note)
    if result is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    db.commit()
    return result


@admin_router.post("/taxonomy/candidates/{candidate_id}/reject", response_model=TaxonomyCandidateDecisionResponse)
def admin_reject_taxonomy_candidate(
    candidate_id: str,
    payload: TaxonomyCandidateDecisionRequest,
    db: Session = Depends(get_db),
) -> TaxonomyCandidateDecisionResponse:
    result = decide_taxonomy_candidate(db, candidate_id=candidate_id, status="rejected", review_note=payload.review_note)
    if result is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    db.commit()
    return result


@router.get("/admin/messages/review/view", response_class=HTMLResponse)
def admin_review_messages_view(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: None = Depends(require_admin_api_key_query_or_cookie),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    data = get_review_messages(db, limit=limit, offset=offset)
    return HTMLResponse(content=_render_admin_review_table_page(data=data, limit=limit, offset=offset))


@router.get("/admin/sentiment/audit/view", response_class=HTMLResponse)
def admin_sentiment_audit_view(
    sample_size: int = Query(default=10, ge=1, le=100),
    _: None = Depends(require_admin_api_key_query_or_cookie),
) -> HTMLResponse:
    return HTMLResponse(content=_render_admin_sentiment_audit_page(sample_size=sample_size))


@router.get("/places/{place_id}/entries", response_model=list[EntryResponse], dependencies=[Depends(require_admin_api_key)])
def get_place_entries(
    place_id: int,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[EntryResponse]:
    return list_place_entries(db, place_id=place_id, limit=limit, offset=offset)


@router.get("/places/{place_id}/threads", response_model=list[ThreadResponse], dependencies=[Depends(require_admin_api_key)])
def get_place_threads(
    place_id: int,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[ThreadResponse]:
    return list_place_threads(db, place_id=place_id, limit=limit, offset=offset)


@router.get(
    "/places/{place_id}/threads/{thread_id}/messages",
    dependencies=[Depends(require_admin_api_key)],
    response_model=list[ThreadTurnResponse],
)
def get_thread_messages(
    place_id: int,
    thread_id: str,
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[ThreadTurnResponse]:
    return list_thread_turns(db, place_id=place_id, thread_id=thread_id, limit=limit, offset=offset)


@admin_router.get("/places/{place_id}/map/points", response_model=MapPointsResponse)
def admin_place_map_points(
    place_id: int,
    period_days: int | None = Query(default=30, ge=1, le=3650),
    limit: int = Query(default=3000, ge=1, le=10000),
    db: Session = Depends(get_db),
) -> MapPointsResponse:
    return get_place_map_points(db, place_id=place_id, limit=limit, period_days=period_days)


@admin_router.get("/sentiment/audit/sample", response_model=SentimentAuditSampleResponse)
def admin_sentiment_audit_sample(
    sample_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
) -> SentimentAuditSampleResponse:
    return get_sentiment_audit_sample(db, sample_size=sample_size)


@admin_router.post("/sentiment/audit/evaluate", response_model=SentimentAuditEvaluateResponse)
def admin_sentiment_audit_evaluate(
    payload: SentimentAuditEvaluateRequest,
    db: Session = Depends(get_db),
) -> SentimentAuditEvaluateResponse:
    result = evaluate_sentiment_audit(db, payload)
    db.commit()
    return result


@admin_router.get("/places/{place_id}/map/heatmap", response_model=HeatmapResponse)
def admin_place_map_heatmap(
    place_id: int,
    mode: str = Query(default="negative"),
    period_days: int | None = Query(default=30, ge=1, le=3650),
    limit: int = Query(default=5000, ge=1, le=20000),
    db: Session = Depends(get_db),
) -> HeatmapResponse:
    return get_place_heatmap(db, place_id=place_id, mode=mode, limit=limit, period_days=period_days)


@admin_router.get("/places/{place_id}/map/grid", response_model=GridResponse)
def admin_place_map_grid(
    place_id: int,
    cell_m: float = Query(default=100.0, ge=20.0, le=1000.0),
    min_points: int = Query(default=1, ge=1, le=100),
    period_days: int | None = Query(default=30, ge=1, le=3650),
    limit: int = Query(default=5000, ge=1, le=50000),
    db: Session = Depends(get_db),
) -> GridResponse:
    return get_place_sentiment_grid(
        db,
        place_id=place_id,
        cell_meters=cell_m,
        period_days=period_days,
        limit=limit,
        min_points=min_points,
    )


@admin_router.get("/places/{place_id}/map/timelapse", response_model=TimelapseResponse)
def admin_place_map_timelapse(
    place_id: int,
    mode: str = Query(default="negative"),
    granularity: str = Query(default="day"),
    period_days: int | None = Query(default=30, ge=1, le=3650),
    limit: int = Query(default=3000, ge=1, le=20000),
    db: Session = Depends(get_db),
) -> TimelapseResponse:
    return get_place_timelapse(
        db,
        place_id=place_id,
        mode=mode,
        granularity=granularity,
        period_days=period_days,
        limit=limit,
    )


@router.get("/admin/places/{place_id}/map/view", response_class=HTMLResponse)
def admin_place_map_view(
    place_id: int,
    period_days: int = Query(default=30, ge=1, le=3650),
    mode: str = Query(default="negative"),
    _: None = Depends(require_admin_api_key_query_or_cookie),
) -> HTMLResponse:
    return HTMLResponse(content=_render_place_map_page(place_id=place_id, period_days=period_days, heatmap_mode=mode))
