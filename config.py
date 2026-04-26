import os


class Config:
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "change-me")
    APP_NAME = os.getenv("APP_NAME", "My App")
    TAILSCALE_IP = os.getenv("TAILSCALE_IP", "127.0.0.1")
    PORT = int(os.getenv("PORT", 5000))
    PROFILES = os.getenv("PROFILES", "Default")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///app.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


configs = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
}
