# backend/studio_core/settings/__init__.py
import os

_module_by_env = {
    "dev": "studio_core.settings.dev",
    "test": "studio_core.settings.test",
    "prod": "studio_core.settings.prod",
    "upgrade": "studio_core.settings.upgrade",
}

# Si DJANGO_SETTINGS_MODULE n’est pas déjà défini (ex: via manage.py ou variables d'env)
if "DJANGO_SETTINGS_MODULE" not in os.environ:
    env = os.getenv("APP_ENV", "dev")
    os.environ["DJANGO_SETTINGS_MODULE"] = _module_by_env.get(env, _module_by_env["dev"])
