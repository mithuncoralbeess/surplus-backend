from .models import SystemSettings, PopupSetting, AdminDetails

def maintenance_mode_context(request):
    """
    Context processor to pass maintenance mode status, popup settings, and admin session context to all templates.
    """
    context_data = {
        "is_maintenance_mode": False,
        "maintenance_message": "Website is under maintenance. Please check back later.",
        "popup_setting": None,
        "pending_admins_count": 0,
    }
    try:
        sys_settings, _ = SystemSettings.objects.get_or_create(id=1)
        popup_setting, _ = PopupSetting.objects.get_or_create(id=1)
        context_data["is_maintenance_mode"] = sys_settings.is_maintenance_mode
        context_data["maintenance_message"] = sys_settings.maintenance_message
        context_data["popup_setting"] = popup_setting

        # Check admin session
        admin_id = request.session.get("adminid")
        if admin_id:
            admin_user = AdminDetails.objects.filter(id=admin_id).first()
            if admin_user:
                is_super = (admin_user.account_type == "SuperAdmin" or admin_user.email == "super@gmail.com")
                context_data["current_admin"] = admin_user
                context_data["is_super_admin"] = is_super
                if is_super:
                    context_data["pending_admins_count"] = AdminDetails.objects.filter(status=False).count()
    except Exception:
        pass

    return context_data

