from datetime import time
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.bookings.models import Booking
from apps.clubs.models import Club, ClubMembership
from apps.courts.models import Court, CourtStaffAssignment, CourtWorkingHour


class BookingAPITestCase(APITestCase):
    password = "test-pass-123"

    def create_user(self, username: str, role: str) -> User:
        return User.objects.create_user(
            username=username,
            password=self.password,
            role=role,
        )

    def create_club(self, name: str, **extra_fields) -> Club:
        data = {
            "name": name,
            "city": "Assiut",
            "area": "Downtown",
        }
        data.update(extra_fields)
        return Club.objects.create(**data)

    def create_court(self, club: Club, name: str, **extra_fields) -> Court:
        data = {
            "club": club,
            "name": name,
            "default_price": Decimal("300.00"),
            "slot_duration_minutes": 60,
        }
        data.update(extra_fields)
        return Court.objects.create(**data)

    def create_membership(self, club: Club, user: User, role: str):
        return ClubMembership.objects.create(
            club=club,
            user=user,
            role=role,
        )

    def create_staff_assignment(self, court: Court, user: User):
        return CourtStaffAssignment.objects.create(court=court, user=user)

    def create_booking(self, court: Court, **extra_fields) -> Booking:
        start_time = extra_fields.pop("start_time", self.time_at(20))
        end_time = extra_fields.pop("end_time", self.time_at(21))
        data = {
            "club": court.club,
            "court": court,
            "customer_name": "Existing Customer",
            "customer_phone": "+201000000001",
            "start_time": start_time,
            "end_time": end_time,
            "total_price": Decimal("300.00"),
            "status": Booking.Status.HOLD,
            "source": Booking.Source.MANUAL,
        }
        data.update(extra_fields)
        return Booking.objects.create(**data)

    def time_at(self, hour: int, minute: int = 0):
        return timezone.datetime(
            2026,
            5,
            20,
            hour,
            minute,
            tzinfo=timezone.get_current_timezone(),
        )

    def booking_payload(self, court: Court, **extra_fields):
        data = {
            "court": court.id,
            "customer_name": "Ahmed Hassan",
            "customer_phone": "+201000000002",
            "start_time": self.time_at(20).isoformat(),
            "end_time": self.time_at(21).isoformat(),
        }
        data.update(extra_fields)
        return data

    def post_booking(self, court: Court, **extra_fields):
        return self.client.post(
            reverse("booking-list"),
            self.booking_payload(court, **extra_fields),
            format="json",
        )

    def list_ids(self, response):
        return {item["id"] for item in response.data["results"]}


class BookingCreationTests(BookingAPITestCase):
    def setUp(self):
        self.platform_admin = self.create_user(
            "booking-admin",
            User.Role.PLATFORM_SUPER_ADMIN,
        )
        self.club = self.create_club("Booking Club")
        self.court = self.create_court(self.club, "Booking Court")

    def test_booking_can_be_created_with_required_fields(self):
        self.client.force_authenticate(user=self.platform_admin)

        response = self.post_booking(self.court)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        booking = Booking.objects.get(id=response.data["id"])
        self.assertEqual(booking.customer_name, "Ahmed Hassan")
        self.assertEqual(str(booking.customer_phone), "+201000000002")

    def test_booking_defaults_to_hold_and_manual_source(self):
        self.client.force_authenticate(user=self.platform_admin)

        response = self.post_booking(self.court)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        booking = Booking.objects.get(id=response.data["id"])
        self.assertEqual(booking.status, Booking.Status.HOLD)
        self.assertEqual(booking.source, Booking.Source.MANUAL)

    def test_total_price_is_calculated_from_court_price_and_duration(self):
        self.client.force_authenticate(user=self.platform_admin)

        response = self.post_booking(
            self.court,
            start_time=self.time_at(20).isoformat(),
            end_time=self.time_at(22).isoformat(),
            total_price="1.00",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        booking = Booking.objects.get(id=response.data["id"])
        self.assertEqual(booking.total_price, Decimal("600.00"))
        self.assertEqual(response.data["total_price"], "600.00")

    def test_club_is_copied_from_court(self):
        self.client.force_authenticate(user=self.platform_admin)

        response = self.post_booking(self.court)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        booking = Booking.objects.get(id=response.data["id"])
        self.assertEqual(booking.club, self.club)
        self.assertEqual(response.data["club"], self.club.id)

    def test_start_time_must_be_before_end_time(self):
        self.client.force_authenticate(user=self.platform_admin)

        response = self.post_booking(
            self.court,
            start_time=self.time_at(21).isoformat(),
            end_time=self.time_at(20).isoformat(),
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_duration_must_match_slot_duration_multiple(self):
        self.client.force_authenticate(user=self.platform_admin)

        response = self.post_booking(
            self.court,
            start_time=self.time_at(20).isoformat(),
            end_time=self.time_at(20, 30).isoformat(),
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_booking_outside_working_hours_is_allowed(self):
        CourtWorkingHour.objects.create(
            court=self.court,
            weekday=2,
            opens_at=time(10, 0),
            closes_at=time(18, 0),
        )
        self.client.force_authenticate(user=self.platform_admin)

        response = self.post_booking(
            self.court,
            start_time=self.time_at(22).isoformat(),
            end_time=self.time_at(23).isoformat(),
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


class BookingScopeTests(BookingAPITestCase):
    def setUp(self):
        self.platform_admin = self.create_user(
            "scope-admin",
            User.Role.PLATFORM_SUPER_ADMIN,
        )
        self.owner = self.create_user("scope-owner", User.Role.CLUB_OWNER)
        self.manager = self.create_user("scope-manager", User.Role.MANAGER)
        self.staff = self.create_user("scope-staff", User.Role.STAFF)
        self.club = self.create_club("Scoped Club")
        self.other_club = self.create_club("Other Scoped Club")
        self.court = self.create_court(self.club, "Scoped Court")
        self.other_court = self.create_court(self.other_club, "Other Scoped Court")
        self.booking = self.create_booking(self.court)
        self.other_booking = self.create_booking(
            self.other_court,
            customer_phone="+201000000003",
        )
        self.create_membership(self.club, self.owner, ClubMembership.Role.OWNER)
        self.create_membership(self.club, self.manager, ClubMembership.Role.MANAGER)
        self.create_staff_assignment(self.court, self.staff)

    def test_anonymous_cannot_access_bookings(self):
        response = self.client.get(reverse("booking-list"))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_platform_super_admin_can_list_all_bookings(self):
        self.client.force_authenticate(user=self.platform_admin)

        response = self.client.get(reverse("booking-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            self.list_ids(response),
            {self.booking.id, self.other_booking.id},
        )

    def test_owner_can_list_bookings_only_for_owned_clubs(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.get(reverse("booking-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.list_ids(response), {self.booking.id})

    def test_manager_can_list_bookings_only_for_assigned_club(self):
        self.client.force_authenticate(user=self.manager)

        response = self.client.get(reverse("booking-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.list_ids(response), {self.booking.id})

    def test_staff_can_list_bookings_only_for_assigned_court(self):
        self.client.force_authenticate(user=self.staff)

        response = self.client.get(reverse("booking-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.list_ids(response), {self.booking.id})

    def test_owner_cannot_retrieve_unrelated_booking(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.get(
            reverse("booking-detail", kwargs={"pk": self.other_booking.pk})
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_manager_cannot_retrieve_unrelated_booking(self):
        self.client.force_authenticate(user=self.manager)

        response = self.client.get(
            reverse("booking-detail", kwargs={"pk": self.other_booking.pk})
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_staff_cannot_retrieve_unrelated_booking(self):
        self.client.force_authenticate(user=self.staff)

        response = self.client.get(
            reverse("booking-detail", kwargs={"pk": self.other_booking.pk})
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class BookingCreationPermissionTests(BookingAPITestCase):
    def setUp(self):
        self.platform_admin = self.create_user(
            "create-admin",
            User.Role.PLATFORM_SUPER_ADMIN,
        )
        self.owner = self.create_user("create-owner", User.Role.CLUB_OWNER)
        self.manager = self.create_user("create-manager", User.Role.MANAGER)
        self.staff = self.create_user("create-staff", User.Role.STAFF)
        self.club = self.create_club("Create Club")
        self.other_club = self.create_club("Other Create Club")
        self.court = self.create_court(self.club, "Create Court")
        self.other_court = self.create_court(self.other_club, "Other Create Court")
        self.create_membership(self.club, self.owner, ClubMembership.Role.OWNER)
        self.create_membership(self.club, self.manager, ClubMembership.Role.MANAGER)
        self.create_staff_assignment(self.court, self.staff)

    def test_platform_super_admin_can_create_booking_on_any_active_court(self):
        self.client.force_authenticate(user=self.platform_admin)

        response = self.post_booking(self.other_court)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_owner_can_create_booking_inside_owned_club(self):
        self.client.force_authenticate(user=self.owner)

        response = self.post_booking(self.court)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_owner_cannot_create_booking_inside_unrelated_club(self):
        self.client.force_authenticate(user=self.owner)

        response = self.post_booking(self.other_court)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_manager_can_create_booking_inside_assigned_club(self):
        self.client.force_authenticate(user=self.manager)

        response = self.post_booking(self.court)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_manager_cannot_create_booking_inside_unrelated_club(self):
        self.client.force_authenticate(user=self.manager)

        response = self.post_booking(self.other_court)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_can_create_booking_on_assigned_court(self):
        self.client.force_authenticate(user=self.staff)

        response = self.post_booking(self.court)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_staff_cannot_create_booking_on_unrelated_court(self):
        self.client.force_authenticate(user=self.staff)

        response = self.post_booking(self.other_court)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class BookingSourceAndActiveTests(BookingAPITestCase):
    def setUp(self):
        self.platform_admin = self.create_user(
            "source-admin",
            User.Role.PLATFORM_SUPER_ADMIN,
        )
        self.owner = self.create_user("source-owner", User.Role.CLUB_OWNER)
        self.club = self.create_club("Source Club")
        self.court = self.create_court(self.club, "Source Court")
        self.create_membership(self.club, self.owner, ClubMembership.Role.OWNER)

    def test_non_platform_users_cannot_create_admin_correction_booking(self):
        self.client.force_authenticate(user=self.owner)

        response = self.post_booking(
            self.court,
            source=Booking.Source.ADMIN_CORRECTION,
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_platform_super_admin_can_create_admin_correction_booking(self):
        self.client.force_authenticate(user=self.platform_admin)

        response = self.post_booking(
            self.court,
            source=Booking.Source.ADMIN_CORRECTION,
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["source"], Booking.Source.ADMIN_CORRECTION)

    def test_normal_booking_source_defaults_to_manual(self):
        self.client.force_authenticate(user=self.platform_admin)

        response = self.post_booking(self.court)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["source"], Booking.Source.MANUAL)

    def test_cannot_create_booking_on_inactive_court(self):
        self.court.is_active = False
        self.court.save(update_fields=["is_active"])
        self.client.force_authenticate(user=self.platform_admin)

        response = self.post_booking(self.court)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_create_booking_when_club_is_inactive(self):
        self.club.is_active = False
        self.club.save(update_fields=["is_active"])
        self.client.force_authenticate(user=self.platform_admin)

        response = self.post_booking(self.court)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class BookingOverlapTests(BookingAPITestCase):
    def setUp(self):
        self.platform_admin = self.create_user(
            "overlap-admin",
            User.Role.PLATFORM_SUPER_ADMIN,
        )
        self.club = self.create_club("Overlap Club")
        self.court = self.create_court(self.club, "Overlap Court")
        self.other_court = self.create_court(self.club, "Other Overlap Court")
        self.client.force_authenticate(user=self.platform_admin)

    def create_existing_booking(self, status_value):
        return self.create_booking(
            self.court,
            start_time=self.time_at(20),
            end_time=self.time_at(21),
            status=status_value,
        )

    def assert_overlap_is_rejected_for_status(self, status_value):
        self.create_existing_booking(status_value)

        response = self.post_booking(
            self.court,
            start_time=self.time_at(20, 30).isoformat(),
            end_time=self.time_at(21, 30).isoformat(),
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def assert_overlap_is_allowed_for_status(self, status_value):
        self.create_existing_booking(status_value)

        response = self.post_booking(
            self.court,
            start_time=self.time_at(20, 30).isoformat(),
            end_time=self.time_at(21, 30).isoformat(),
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_cannot_create_overlapping_hold_booking_on_same_court(self):
        self.assert_overlap_is_rejected_for_status(Booking.Status.HOLD)

    def test_cannot_create_overlapping_confirmed_booking_on_same_court(self):
        self.assert_overlap_is_rejected_for_status(Booking.Status.CONFIRMED)

    def test_can_create_adjacent_booking_ending_exactly_at_existing_start(self):
        self.create_existing_booking(Booking.Status.HOLD)

        response = self.post_booking(
            self.court,
            start_time=self.time_at(19).isoformat(),
            end_time=self.time_at(20).isoformat(),
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_can_create_adjacent_booking_starting_exactly_at_existing_end(self):
        self.create_existing_booking(Booking.Status.HOLD)

        response = self.post_booking(
            self.court,
            start_time=self.time_at(21).isoformat(),
            end_time=self.time_at(22).isoformat(),
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_can_create_overlapping_booking_on_different_court(self):
        self.create_existing_booking(Booking.Status.HOLD)

        response = self.post_booking(
            self.other_court,
            start_time=self.time_at(20, 30).isoformat(),
            end_time=self.time_at(21, 30).isoformat(),
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_cancelled_booking_does_not_block_slot(self):
        self.assert_overlap_is_allowed_for_status(Booking.Status.CANCELLED)

    def test_expired_booking_does_not_block_slot(self):
        self.assert_overlap_is_allowed_for_status(Booking.Status.EXPIRED)

    def test_completed_booking_does_not_block_slot(self):
        self.assert_overlap_is_allowed_for_status(Booking.Status.COMPLETED)

    def test_no_show_booking_does_not_block_slot(self):
        self.assert_overlap_is_allowed_for_status(Booking.Status.NO_SHOW)


class BookingUpdateTests(BookingAPITestCase):
    def setUp(self):
        self.platform_admin = self.create_user(
            "update-admin",
            User.Role.PLATFORM_SUPER_ADMIN,
        )
        self.club = self.create_club("Update Club")
        self.court = self.create_court(self.club, "Update Court")
        self.other_court = self.create_court(self.club, "Other Update Court")
        self.booking = self.create_booking(self.court)
        self.client.force_authenticate(user=self.platform_admin)

    def test_allowed_user_can_patch_basic_details(self):
        response = self.client.patch(
            reverse("booking-detail", kwargs={"pk": self.booking.pk}),
            {
                "customer_name": "Updated Customer",
                "customer_phone": "+201000000004",
                "notes": "Updated note",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.customer_name, "Updated Customer")
        self.assertEqual(str(self.booking.customer_phone), "+201000000004")
        self.assertEqual(self.booking.notes, "Updated note")

    def test_cannot_patch_status_in_sprint_3(self):
        response = self.client.patch(
            reverse("booking-detail", kwargs={"pk": self.booking.pk}),
            {"status": Booking.Status.CANCELLED},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.HOLD)

    def test_cannot_patch_total_price(self):
        response = self.client.patch(
            reverse("booking-detail", kwargs={"pk": self.booking.pk}),
            {"total_price": "1.00"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.total_price, Decimal("300.00"))

    def test_cannot_patch_court_or_times_in_sprint_3(self):
        original_start = self.booking.start_time
        original_end = self.booking.end_time

        response = self.client.patch(
            reverse("booking-detail", kwargs={"pk": self.booking.pk}),
            {
                "court": self.other_court.id,
                "start_time": self.time_at(22).isoformat(),
                "end_time": self.time_at(23).isoformat(),
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.court, self.court)
        self.assertEqual(self.booking.start_time, original_start)
        self.assertEqual(self.booking.end_time, original_end)

    def test_delete_booking_is_not_allowed(self):
        response = self.client.delete(
            reverse("booking-detail", kwargs={"pk": self.booking.pk})
        )

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_locked_booking_status_cannot_be_patched(self):
        self.booking.status = Booking.Status.COMPLETED
        self.booking.save(update_fields=["status"])

        response = self.client.patch(
            reverse("booking-detail", kwargs={"pk": self.booking.pk}),
            {"customer_name": "Should Not Change"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class BookingFilterTests(BookingAPITestCase):
    def setUp(self):
        self.platform_admin = self.create_user(
            "filter-admin",
            User.Role.PLATFORM_SUPER_ADMIN,
        )
        self.owner = self.create_user("filter-owner", User.Role.CLUB_OWNER)
        self.club = self.create_club("Filter Club")
        self.other_club = self.create_club("Other Filter Club")
        self.court = self.create_court(self.club, "Filter Court")
        self.other_court = self.create_court(self.other_club, "Other Filter Court")
        self.create_membership(self.club, self.owner, ClubMembership.Role.OWNER)
        self.booking = self.create_booking(
            self.court,
            start_time=self.time_at(20),
            end_time=self.time_at(21),
            status=Booking.Status.HOLD,
            source=Booking.Source.MANUAL,
        )
        self.confirmed_booking = self.create_booking(
            self.court,
            customer_phone="+201000000005",
            start_time=self.time_at(22),
            end_time=self.time_at(23),
            status=Booking.Status.CONFIRMED,
            source=Booking.Source.ADMIN_CORRECTION,
        )
        self.other_booking = self.create_booking(
            self.other_court,
            customer_phone="+201000000006",
            start_time=self.time_at(20),
            end_time=self.time_at(21),
            status=Booking.Status.HOLD,
        )
        self.client.force_authenticate(user=self.platform_admin)

    def test_filter_by_court(self):
        response = self.client.get(reverse("booking-list"), {"court": self.court.id})

        self.assertEqual(
            self.list_ids(response),
            {self.booking.id, self.confirmed_booking.id},
        )

    def test_filter_by_club(self):
        response = self.client.get(reverse("booking-list"), {"club": self.club.id})

        self.assertEqual(
            self.list_ids(response),
            {self.booking.id, self.confirmed_booking.id},
        )

    def test_filter_by_status(self):
        response = self.client.get(
            reverse("booking-list"),
            {"status": Booking.Status.CONFIRMED},
        )

        self.assertEqual(self.list_ids(response), {self.confirmed_booking.id})

    def test_filter_by_source(self):
        response = self.client.get(
            reverse("booking-list"),
            {"source": Booking.Source.ADMIN_CORRECTION},
        )

        self.assertEqual(self.list_ids(response), {self.confirmed_booking.id})

    def test_filter_by_date(self):
        response = self.client.get(reverse("booking-list"), {"date": "2026-05-20"})

        self.assertEqual(
            self.list_ids(response),
            {self.booking.id, self.confirmed_booking.id, self.other_booking.id},
        )

    def test_filter_by_date_from_and_date_to(self):
        response = self.client.get(
            reverse("booking-list"),
            {
                "date_from": self.time_at(21, 30).isoformat(),
                "date_to": self.time_at(22, 30).isoformat(),
            },
        )

        self.assertEqual(self.list_ids(response), {self.confirmed_booking.id})

    def test_filters_still_respect_user_scope(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.get(reverse("booking-list"), {"date": "2026-05-20"})

        self.assertEqual(
            self.list_ids(response),
            {self.booking.id, self.confirmed_booking.id},
        )
        self.assertNotIn(self.other_booking.id, self.list_ids(response))
