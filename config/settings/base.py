from pathlib import Path

from pytz import VERSION
from dotenv import load_dotenv
from os import getenv, path
from loguru import logger
from datetime import timedelta

# build paths inside the project like this: BASE

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve(strict=True).parent.parent.parent

APP_DIR = BASE_DIR / "core_apps"

localenv_file = path.join(BASE_DIR, ".envs", "env.local")


# Application definition

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "django.contrib.humanize",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "django_countries",
    "phonenumber_field",
    "django_filters",
    "djoser",
    "cloudinary",
    "drf_spectacular",
    "django_celery_beat",
    "djcelery_email",
]

LOCAL_APPS = ["core_apps.common", "core_apps.user_auth", "core_apps.user_profile"]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core_apps.user_auth.middleware.CustomHeaderMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [str(BASE_DIR / "templates")],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": getenv("POSTGRES_DB"),
        "USER": getenv("POSTGRES_USER"),
        "PASSWORD": getenv("POSTGRES_PASSWORD"),
        "HOST": getenv("POSTGRES_HOST"),
        "PORT": getenv("POSTGRES_PORT"),
    }
}

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
    "django.contrib.auth.hashers.BCryptPasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True

SITE_ID = 1


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "user_auth.User"

REST_FRAMEWORK = {"DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema"}

SPECTACULAR_SETTINGS = {
    "TITLE": "Next Gen Bank API",
    "DESCRIPTION": "AN API build for a banking system",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "LICENCE": {"name": "MIT LIcence", "url": "https://opensourse.org/license/mit"},
}

LOGGING_CONFIG = None


LOGURU_LOGGING = {
    "handlers": [
        {
            "sink": BASE_DIR / "logs/debug.log",
            "rotation": "10MB",
            "level": "DEBUG",
            "filter": lambda record: record["level"].no <= logger.level("WARNING").no,
            "format": "{time:YYYY-MM-DD at HH:mm:ss} | {level: <8} |{name}:{function}:{line} - {message}",
            "retention": "30 days",
            "compression": "zip",
        },
        {
            "sink": BASE_DIR / "logs/error.log",
            "rotation": "10MB",
            "level": "ERROR",
            "format": "{time:YYYY-MM-DD at HH:mm:ss} | {level: <8} |{name}:{function}:{line} - {message}",
            "retention": "30 days",
            "compression": "zip",
            "backtrace": True,
            "diagnose": True,
        },
    ]
}


logger.configure(**LOGURU_LOGGING)


LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"loguru": {"class": "config.interceptor.InterceptHandler"}},
    "root": {
        "handlers": ["loguru"],
        "level": "DEBUG",
    },
}
