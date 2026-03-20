import os
import importlib
import config

def test_default_config():
    # Tests that config loads properly without a .env file
    assert config.API_PORT == 8000
    assert config.EMBED_DIMENSION == 384
    assert config.OCR_LANGUAGE == "en"

def test_config_override(monkeypatch):
    monkeypatch.setenv("API_PORT", "9000")
    monkeypatch.setenv("MAX_FILE_SIZE_MB", "100")
    
    # Reload the config module to pick up monkeypatched env vars
    importlib.reload(config)
    
    assert config.API_PORT == 9000
    assert config.MAX_FILE_SIZE_MB == 100
    
    # Cleanup for other tests
    monkeypatch.delenv("API_PORT", raising=False)
    monkeypatch.delenv("MAX_FILE_SIZE_MB", raising=False)
    importlib.reload(config)
