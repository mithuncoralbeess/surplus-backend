from django.core.cache import cache
from django.db.models import Q
from .models import (
    SystemSettings,
    PopupSetting,
    AdminDetails,
    AdminNotification,
    Lot,
    Product,
    RfqEnquiry,
    ContactUsEnquiry,
)

def maintenance_mode_context(request):
    """
    Context processor to pass maintenance mode status, popup settings,
    sidebar pending counts, and admin session context to all templates.
    Optimized with short-term caching (30s) to eliminate redundant remote DB latency on every page request.
    """
    context_data = {
        "is_maintenance_mode": False,
        "maintenance_message": "Website is under maintenance. Please check back later.",
        "popup_setting": None,
        "pending_admins_count": 0,
        "pending_lots_count": 0,
        "pending_seller_enquiries_count": 0,
        "pending_rfqs_count": 0,
        "pending_general_enquiries_count": 0,
        "admin_unread_notifications_count": 0,
        "admin_recent_notifications": [],
    }
    try:
        # Cache global settings and sidebar pending badges for 30s
        global_cache_key = "ctx_proc_global_counts_v1"
        global_info = cache.get(global_cache_key)
        if global_info is None:
            sys_settings = SystemSettings.objects.filter(id=1).first()
            if not sys_settings:
                sys_settings, _ = SystemSettings.objects.get_or_create(id=1)

            popup_setting = PopupSetting.objects.filter(id=1).first()
            if not popup_setting:
                popup_setting, _ = PopupSetting.objects.get_or_create(id=1)

            pending_lots = Lot.objects.filter(enquiry_status__iexact="pending").count()
            pending_seller = Product.objects.filter(enquiry_status__iexact="pending").count()
            pending_rfqs = RfqEnquiry.objects.filter(status__iexact="pending").count()
            pending_general = ContactUsEnquiry.objects.filter(status__iexact="pending").count()

            global_info = {
                "is_maintenance_mode": sys_settings.is_maintenance_mode,
                "maintenance_message": sys_settings.maintenance_message,
                "popup_setting": popup_setting,
                "pending_lots_count": pending_lots,
                "pending_seller_enquiries_count": pending_seller,
                "pending_rfqs_count": pending_rfqs,
                "pending_general_enquiries_count": pending_general,
            }
            cache.set(global_cache_key, global_info, timeout=30)

        context_data.update(global_info)

        # Check admin session with cache
        admin_id = request.session.get("adminid")
        if admin_id:
            admin_user_cache_key = f"ctx_admin_user_{admin_id}"
            admin_user = cache.get(admin_user_cache_key)
            if admin_user is None:
                admin_user = AdminDetails.objects.filter(id=admin_id).first()
                if admin_user:
                    cache.set(admin_user_cache_key, admin_user, timeout=60)

            if admin_user:
                is_super = (admin_user.account_type == "SuperAdmin" or admin_user.email == "super@gmail.com")
                context_data["current_admin"] = admin_user
                context_data["is_super_admin"] = is_super

                notif_cache_key = f"ctx_admin_notifs_{admin_id}"
                cached_notifs = cache.get(notif_cache_key)
                if cached_notifs is None:
                    pending_admins = AdminDetails.objects.filter(status=False).count() if is_super else 0
                    if is_super:
                        notif_qs = AdminNotification.objects.filter(
                            Q(admin=admin_user) | Q(for_superadmins_only=True) | Q(admin__isnull=True)
                        )
                    else:
                        notif_qs = AdminNotification.objects.filter(
                            Q(admin=admin_user) | (Q(admin__isnull=True) & Q(for_superadmins_only=False))
                        )
                    unread_count = notif_qs.filter(is_read=False).count()
                    recent_notifs = list(notif_qs[:12])
                    cached_notifs = {
                        "pending_admins_count": pending_admins,
                        "admin_unread_notifications_count": unread_count,
                        "admin_recent_notifications": recent_notifs,
                    }
                    cache.set(notif_cache_key, cached_notifs, timeout=20)

                context_data.update(cached_notifs)
    except Exception:
        pass

    return context_data
