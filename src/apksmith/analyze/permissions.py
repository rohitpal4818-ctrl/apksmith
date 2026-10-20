"""
Permission analysis.

Two ideas matter here:

1. **Risk weighting.** Not all permissions are equal. ``INTERNET`` is
   unremarkable; ``READ_SMS`` or ``CAMERA`` is worth a human's attention.

2. **Declared vs used.** A permission in the manifest is a *claim*. Whether the
   app actually touches the matching API is *evidence*. We check for the API
   in the DEX string pool and record both, because a declared-but-unused
   dangerous permission is a privacy smell, and an obviously-needed-but-missing
   one is a bug.

The reference table is intentionally small and hand-maintained. A generated
table from the platform manifest contains hundreds of entries nobody reads.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models import Category, Confidence, Finding, PermissionUse, Severity

ANDROID = "android.permission."


@dataclass(frozen=True)
class PermSpec:
    """Static knowledge about one permission."""

    severity: Severity
    reason: str
    #: Substrings searched for in the DEX string pool as evidence of use.
    api_markers: tuple[str, ...] = ()


#: Hand-curated risk table. Ordered roughly by how much damage misuse causes.
_PERMISSIONS: dict[str, PermSpec] = {
    "READ_SMS": PermSpec(
        Severity.CRITICAL,
        "Can read every SMS message on the device, including 2FA codes.",
        ("SmsManager", "getMessageBody", "Telephony.Sms", "pdus"),
    ),
    "RECEIVE_SMS": PermSpec(
        Severity.CRITICAL,
        "Can intercept incoming SMS silently.",
        ("SmsReceiver", "pdus", "SMS_RECEIVED"),
    ),
    "SEND_SMS": PermSpec(
        Severity.HIGH,
        "Can send SMS, which costs the user money and can send scams.",
        ("SmsManager", "sendTextMessage", "sendMultipartTextMessage"),
    ),
    "READ_CALL_LOG": PermSpec(
        Severity.CRITICAL,
        "Reads the full call history.",
        ("CallLog", "CallLog.Calls"),
    ),
    "RECORD_AUDIO": PermSpec(
        Severity.HIGH,
        "Can record from the microphone.",
        ("MediaRecorder", "AudioRecord", "RECORD_AUDIO"),
    ),
    "CAMERA": PermSpec(
        Severity.HIGH,
        "Can take photos and video.",
        ("CameraManager", "Camera2", "Camera.open"),
    ),
    "ACCESS_FINE_LOCATION": PermSpec(
        Severity.HIGH,
        "Precise GPS location.",
        ("FusedLocationProviderClient", "LocationManager", "getLastKnownLocation"),
    ),
    "ACCESS_COARSE_LOCATION": PermSpec(
        Severity.MEDIUM,
        "Approximate location.",
        ("LocationManager", "getLastKnownLocation"),
    ),
    "ACCESS_BACKGROUND_LOCATION": PermSpec(
        Severity.HIGH,
        "Location tracking while the app is closed.",
        ("ACCESS_BACKGROUND_LOCATION",),
    ),
    "READ_CONTACTS": PermSpec(
        Severity.HIGH,
        "Reads the full contact list.",
        ("ContactsContract", "ContentResolver"),
    ),
    "WRITE_CONTACTS": PermSpec(
        Severity.MEDIUM,
        "Can modify or delete contacts.",
        ("ContactsContract",),
    ),
    "READ_EXTERNAL_STORAGE": PermSpec(
        Severity.MEDIUM,
        "Reads files on shared storage.",
        ("getExternalStorageDirectory", "Environment"),
    ),
    "WRITE_EXTERNAL_STORAGE": PermSpec(
        Severity.MEDIUM,
        "Writes to shared storage.",
        ("getExternalStorageDirectory",),
    ),
    "MANAGE_EXTERNAL_STORAGE": PermSpec(
        Severity.HIGH,
        "Full access to all shared storage, bypassing scoped storage.",
        ("MANAGE_EXTERNAL_STORAGE",),
    ),
    "READ_PHONE_STATE": PermSpec(
        Severity.MEDIUM,
        "Reads device identifiers and call state.",
        ("TelephonyManager", "getDeviceId", "getImei", "getLine1Number"),
    ),
    "CALL_PHONE": PermSpec(
        Severity.HIGH,
        "Can place calls without the user tapping.",
        ("ACTION_CALL",),
    ),
    "PROCESS_OUTGOING_CALLS": PermSpec(
        Severity.HIGH,
        "Can see and redirect outgoing calls.",
        ("OutgoingCall", "PHONE_STATE"),
    ),
    "BODY_SENSORS": PermSpec(
        Severity.MEDIUM,
        "Reads heart rate and other body sensors.",
        ("SensorManager", "BODY_SENSORS"),
    ),
    "GET_ACCOUNTS": PermSpec(
        Severity.MEDIUM,
        "Reads the list of accounts on the device, including Google accounts.",
        ("AccountManager", "getAccounts"),
    ),
    "BIND_ACCESSIBILITY_SERVICE": PermSpec(
        Severity.HIGH,
        "Accessibility access lets the app read the screen and act on taps. "
        "This is the permission most abused by spyware.",
        ("AccessibilityService",),
    ),
    "BIND_DEVICE_ADMIN": PermSpec(
        Severity.HIGH,
        "Device administrator rights, including the ability to lock the screen.",
        ("DeviceAdminReceiver",),
    ),
    "REQUEST_INSTALL_PACKAGES": PermSpec(
        Severity.HIGH,
        "Can silently ask to install other APKs.",
        ("ACTION_INSTALL_PACKAGE", "REQUEST_INSTALL_PACKAGES"),
    ),
    "SYSTEM_ALERT_WINDOW": PermSpec(
        Severity.MEDIUM,
        "Draws overlays on top of other apps. Used for tapjacking.",
        ("TYPE_APPLICATION_OVERLAY", "SYSTEM_ALERT_WINDOW"),
    ),
    "INTERNET": PermSpec(
        Severity.LOW,
        "Network access. Expected in most apps, worth noting for privacy review.",
        ("HttpURLConnection", "okhttp3", "OkHttpClient", "java.net.URL"),
    ),
    "ACCESS_NETWORK_STATE": PermSpec(
        Severity.INFO,
        "Reads the current network type.",
        ("ConnectivityManager",),
    ),
    "ACCESS_WIFI_STATE": PermSpec(
        Severity.INFO,
        "Reads WiFi state and scan results.",
        ("WifiManager",),
    ),
    "VIBRATE": PermSpec(Severity.INFO, "Vibrates the device.", ()),
    "WAKE_LOCK": PermSpec(Severity.INFO, "Keeps the CPU awake.", ("WakeLock",)),
    "RECEIVE_BOOT_COMPLETED": PermSpec(
        Severity.LOW,
        "Starts automatically on device boot.",
        ("BOOT_COMPLETED",),
    ),
    "FOREGROUND_SERVICE": PermSpec(
        Severity.LOW,
        "Runs a persistent foreground service.",
        ("ForegroundService",),
    ),
    "QUERY_ALL_PACKAGES": PermSpec(
        Severity.MEDIUM,
        "Can enumerate every app installed on the device.",
        ("QUERY_ALL_PACKAGES", "getInstalledPackages"),
    ),
    "USE_SIP": PermSpec(
        Severity.HIGH,
        "Can make VoIP calls over the network.",
        ("SipManager", "SipAudioDevice"),
    ),
    "READ_MEDIA_IMAGES": PermSpec(
        Severity.MEDIUM,
        "Reads the photo library.",
        ("MediaStore",),
    ),
    "SCHEDULE_EXACT_ALARM": PermSpec(
        Severity.MEDIUM,
        "Can schedule alarms that fire at exact times, even when idle.",
        ("AlarmManager", "setExactAndAllowWhileIdle"),
    ),
}

#: Anything not in the table still gets reported, just at low severity.
_DEFAULT = PermSpec(
    Severity.LOW,
    "Declared permission with no specific risk rule.",
    (),
)


def _spec_for(permission: str) -> PermSpec:
    """Look up a permission, tolerating fully-qualified names."""
    short = permission.split(".")[-1] if "." in permission else permission
    return _PERMISSIONS.get(short, _DEFAULT)


def analyse_permissions(loaded) -> tuple[list[PermissionUse], list[Finding]]:
    """Build permission records and findings from a loaded APK."""
    apk = loaded.apk
    printable = loaded.dex.printable_strings

    try:
        declared = list(apk.get_permissions())
    except Exception:
        declared = []

    permissions: list[PermissionUse] = []
    findings: list[Finding] = []

    for perm in sorted(set(declared)):
        spec = _spec_for(perm)

        # Evidence of real use: any of the spec's API markers present in the
        # DEX string pool.
        marker_hit = next(
            (m for m in spec.api_markers if any(m in s for s in printable)), None
        )
        if not spec.api_markers:
            referenced = None  # nothing to check for
        else:
            referenced = marker_hit is not None

        permissions.append(
            PermissionUse(
                name=perm,
                severity=spec.severity,
                reason=spec.reason,
                referenced_in_code=referenced,
            )
        )

        # Only raise a finding once a dangerous permission clears MEDIUM --
        # INFO-level declarations are noise in a report.
        if spec.severity.weight >= 15:
            findings.append(
                Finding(
                    category=Category.PERMISSION,
                    title=f"{perm.split('.')[-1]} declared",
                    detail=spec.reason,
                    severity=spec.severity,
                    confidence=Confidence.HIGH,
                    evidence=[marker_hit] if marker_hit else [],
                    location="AndroidManifest.xml",
                    metadata={
                        "permission": perm,
                        "referenced_in_code": referenced,
                    },
                )
            )

    permissions.sort(key=lambda p: (-p.severity.weight, p.name))
    return permissions, findings
