from django.contrib.auth.models import AbstractUser
from django.db import models
from phonenumber_field.modelfields import PhoneNumberField


class User(AbstractUser):
    class Role(models.TextChoices):
        PLATFORM_SUPER_ADMIN = (
            "PLATFORM_SUPER_ADMIN",
            "Platform super admin",
        )
        CLUB_OWNER = "CLUB_OWNER", "Club owner"
        MANAGER = "MANAGER", "Manager"
        STAFF = "STAFF", "Staff"

    role = models.CharField(max_length=32, choices=Role.choices)
    phone_number = PhoneNumberField(blank=True, null=True)
    created_by = models.ForeignKey(
        "self",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="created_users",
    )

    REQUIRED_FIELDS = ["email", "role"]

    def is_platform_super_admin(self) -> bool:
        return self.role == self.Role.PLATFORM_SUPER_ADMIN

    def is_club_owner(self) -> bool:
        return self.role == self.Role.CLUB_OWNER

    def is_manager(self) -> bool:
        return self.role == self.Role.MANAGER

    def is_staff_member(self) -> bool:
        return self.role == self.Role.STAFF
