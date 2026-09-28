from .models import SystemSettings, PopupSetting

def maintenance_mode_context(request):
    """
    Context processor to pass maintenance mode status and popup settings to all templates.
    """
    try:
        sys_settings, _ = SystemSettings.objects.get_or_create(id=1)
        popup_setting, _ = PopupSetting.objects.get_or_create(id=1)
        return {
            "is_maintenance_mode": sys_settings.is_maintenance_mode,
            "maintenance_message": sys_settings.maintenance_message,
            "popup_setting": popup_setting,
        }
    except Exception:
        return {
            "is_maintenance_mode": False,
            "maintenance_message": "Website is under maintenance. Please check back later.",
            "popup_setting": None,
        }

