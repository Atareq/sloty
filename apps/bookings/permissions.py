from django.db.models import Q
from rest_framework.permissions import BasePermission

from apps.bookings.models import Booking
from apps.clubs.models import ClubMembership
from apps.clubs.permissions import is_active_club_manager, is_active_club_owner
from apps.courts.permissions import is_active_court_staff


def scoped_bookings_for_user(user):
    if not user.is_authenticated:
        return Booking.objects.none()
    if user.is_platform_super_admin():
        return Booking.objects.all()

    scope_filter = Q()
    if user.is_club_owner():
        scope_filter |= Q(
            club__memberships__user=user,
            club__memberships__role=ClubMembership.Role.OWNER,
            club__memberships__is_active=True,
        )
    if user.is_manager():
        scope_filter |= Q(
            club__memberships__user=user,
            club__memberships__role=ClubMembership.Role.MANAGER,
            club__memberships__is_active=True,
        )
    if user.is_staff_member():
        scope_filter |= Q(
            court__staff_assignments__user=user,
            court__staff_assignments__is_active=True,
        )

    if not scope_filter:
        return Booking.objects.none()
    return Booking.objects.filter(scope_filter).distinct()


def can_create_booking_for_court(user, court) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_platform_super_admin():
        return True
    if user.is_club_owner():
        return is_active_club_owner(user, court.club)
    if user.is_manager():
        return is_active_club_manager(user, court.club)
    if user.is_staff_member():
        return is_active_court_staff(user, court)
    return False


class CanManageBookings(BasePermission):
    def has_permission(self, request, view) -> bool:
        user = request.user
        if not user.is_authenticated:
            return False
        return (
            user.is_platform_super_admin()
            or user.is_club_owner()
            or user.is_manager()
            or user.is_staff_member()
        )

    def has_object_permission(self, request, view, obj) -> bool:
        user = request.user
        if not user.is_authenticated:
            return False
        if user.is_platform_super_admin():
            return True
        if user.is_club_owner():
            return is_active_club_owner(user, obj.club)
        if user.is_manager():
            return is_active_club_manager(user, obj.club)
        if user.is_staff_member():
            return is_active_court_staff(user, obj.court)
        return False
