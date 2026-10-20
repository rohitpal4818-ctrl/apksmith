"""
Third-party SDK fingerprinting.

Apps are mostly assembled from known SDKs. Identifying them cheaply tells you
a lot about an app's behaviour before reading a single line of its own code,
and it gives a behaviour-reconstruction pipeline a head start: if we know the
app embeds Firebase Analytics, we do not need to reverse-engineer analytics.

Fingerprints are matched on package-name prefixes found in the DEX class
table. That is fast and precise enough for high-value SDKs, but it will miss
an SDK that ships under an unusual namespace.
"""

from __future__ import annotations

from ..models import ThirdPartySDK

#: (class/package prefix, display name, category, human note)
_SDK_SIGNATURES: list[tuple[str, str, str, str]] = [
    # Analytics / attribution
    (
        "Lcom/google/firebase/analytics",
        "Firebase Analytics",
        "analytics",
        "Google event tracking",
    ),
    (
        "Lcom/google/firebase/messaging",
        "Firebase Cloud Messaging",
        "messaging",
        "Push notifications",
    ),
    (
        "Lcom/google/firebase/crashlytics",
        "Firebase Crashlytics",
        "crash-reporting",
        "Crash and error reporting",
    ),
    ("Lcom/google/firebase/auth", "Firebase Auth", "auth", "Google-backed sign-in"),
    (
        "Lcom/google/firebase/firestore",
        "Cloud Firestore",
        "database",
        "Google NoSQL database",
    ),
    ("Lcom/google/android/gms/ads", "Google AdMob", "ads", "Advertising"),
    (
        "Lcom/google/android/gms/ads/identifier",
        "Google Advertising ID",
        "ads",
        "Device advertising identifier",
    ),
    ("Lcom/facebook/ads", "Meta Audience Network", "ads", "Meta advertising"),
    ("Lcom/facebook/", "Facebook SDK", "social", "Facebook integration"),
    ("Lcom/amplitude/", "Amplitude", "analytics", "Product analytics"),
    ("Lcom/mixpanel/", "Mixpanel", "analytics", "Product analytics"),
    ("Lcom/segment/", "Segment", "analytics", "Customer data platform"),
    ("Lcom/appsflyer/", "AppsFlyer", "attribution", "Install attribution"),
    ("Lcom/adjust/", "Adjust", "attribution", "Install attribution"),
    ("Lcom/branch/", "Branch", "attribution", "Deep-link attribution"),
    # Crash reporting
    ("Lcom/crashlytics/", "Crashlytics (legacy)", "crash-reporting", "Crash reporting"),
    ("Lcom/bugsnag/", "Bugsnag", "crash-reporting", "Crash reporting"),
    ("Lio/sentry/", "Sentry", "crash-reporting", "Crash reporting"),
    # Payments
    ("Lcom/stripe/", "Stripe", "payments", "Card payments"),
    ("Lcom/razorpay/", "Razorpay", "payments", "Indian payments"),
    ("Lcom/paypal/", "PayPal", "payments", "PayPal payments"),
    # Networking
    ("Lokhttp3/", "OkHttp", "networking", "HTTP client"),
    ("Lokhttp/", "OkHttp 2", "networking", "HTTP client"),
    ("Lretrofit2/", "Retrofit", "networking", "Typed HTTP client"),
    ("Lcom/squareup/okhttp3", "OkHttp 3", "networking", "HTTP client"),
    ("Lcom/google/gson/", "Gson", "serialization", "JSON serialization"),
    # Storage / ORM
    ("Landroidx/room/", "Room", "database", "Android ORM"),
    ("Lio/realm/", "Realm", "database", "Local database"),
    (
        "Lcom/google/protobuf/",
        "Protocol Buffers",
        "serialization",
        "Binary serialization",
    ),
    # UI kits
    ("Lcom/facebook/react/", "React Native", "ui", "Cross-platform UI"),
    ("Lio/flutter/", "Flutter", "ui", "Cross-platform UI"),
    ("Lcom/airbnb/lottie/", "Lottie", "ui", "Vector animations"),
    # Other common
    ("Lorg/acra/", "ACRA", "crash-reporting", "Open-source crash reporting"),
    ("Lcom/google/gms/auth/api/signin/", "Google Sign-In", "auth", "Google sign-in"),
    ("Landroidx/work/", "WorkManager", "background", "Scheduled background work"),
    ("Landroidx/navigation/", "AndroidX Navigation", "ui", "Screen navigation"),
    ("Lcom/squareup/picasso/", "Picasso", "ui", "Image loading"),
    ("Lcom/bumptech/glide/", "Glide", "ui", "Image loading"),
    ("Lcom/tencent/mm/", "WeChat SDK", "social", "WeChat integration"),
    ("Lcom/whatsapp/", "WhatsApp SDK", "social", "WhatsApp sharing"),
]


def analyse_sdks(loaded) -> list[ThirdPartySDK]:
    """Identify bundled SDKs from DEX class-name prefixes."""
    classes = loaded.dex.classes
    found: list[ThirdPartySDK] = []
    seen: set[str] = set()

    for prefix, name, category, _note in _SDK_SIGNATURES:
        if name in seen:
            continue
        # Count how much of the SDK is present. A single class may be a stub;
        # a few dozen indicates real use.
        hits = [c for c in classes if c.startswith(prefix)]
        if len(hits) >= 3:
            seen.add(name)
            found.append(
                ThirdPartySDK(
                    name=name,
                    category=category,
                    evidence=[f"{len(hits)} classes matching {prefix}"],
                )
            )

    found.sort(key=lambda s: (s.category, s.name))
    return found
