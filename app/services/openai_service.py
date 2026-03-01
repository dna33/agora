from app.services.model_service import ModelService

# Backward-compat shim. Remove once all imports use model_service.
OpenAIService = ModelService
