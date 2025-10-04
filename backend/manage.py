#!/usr/bin/env python
import os
import sys


def main():
    """Point d'entrée Django."""
    # Valeur par défaut raisonnable pour le dev local
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "studio_core.settings.dev")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
