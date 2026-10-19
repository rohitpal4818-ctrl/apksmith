# F-Droid

**Purpose.** F-Droid is an installable catalogue of FOSS (Free and Open Source Software) applications for Android, allowing users to browse, install, and update apps from multiple repositories, including peer-to-peer nearby sharing without internet.

**For.** Android users who prefer free and open source software, privacy-conscious users, and developers distributing FOSS apps.

## Screens

### Onboarding flows
Show first-time guidance for main app areas, updates, filters, repositories, repo details, app issues, and anti-features

**Shows:** Contextual tips or overlays for each onboarding topic
**Actions:** Dismiss onboarding once seen, Progress through multiple onboarding steps

<sub>inferred from: org.fdroid.settings.OnboardingManager (confidence: high)</sub>

### Main app screen
Entry point that initializes settings and notification managers, handles intents and permission requests; provides tabbed navigation to Discover, Search, My Apps, and Repositories

**Shows:** Tab bar with Discover, Search, My Apps, Repositories, App list (implied), Onboarding (implied)
**Actions:** Launch app, Handle new intents, Request POST_NOTIFICATIONS permission, Navigate between tabs

<sub>inferred from: org.fdroid.MainActivity, org.fdroid.ui.navigation.NavigationKey (confidence: high)</sub>

### App list screen
Displays filterable, sortable list of apps from repositories with category, anti-feature, and repository filters; supports drag-and-drop reordering of items

**Shows:** App list items with icons, names, summaries, Filter controls (categories, anti-features, repositories, incompatible toggle), Sort options, Draggable list items with visual feedback
**Actions:** Load apps, Toggle filter visibility, Sort list, Toggle incompatible filter, Add/remove category filter, Add/remove repository filter, Drag item to new position, Drop to reorder, Auto-scroll while dragging near edges

<sub>inferred from: org.fdroid.ui.lists.AppListViewModel, org.fdroid.ui.utils.DragDropState, org.fdroid.ui.navigation.NavigationKey (confidence: high)</sub>

### App details screen
Show detailed information about an app including description, screenshots, versions, and install actions

**Shows:** App icon and feature graphic, Description and summary, Phone screenshots, Categories, Available versions, Install/update/uninstall actions, Anti-features, Author info, Issue tracker link, Proxy info
**Actions:** Install or update app, View version history, Open issue tracker, Share app, View anti-features

<sub>inferred from: org.fdroid.ui.details.LoadedAppDetailsItem, org.fdroid.ui.navigation.NavigationKey (confidence: high)</sub>

### Add Repository Preview
Shows a preview of a repository's apps and metadata before the user confirms adding it

**Shows:** Repository name, App list with names, package names, summaries, and icons, Repo ID
**Actions:** Confirm adding the repository, Cancel

<sub>inferred from: org.fdroid.ui.repositories.add.AddRepoPreviewScreenKt (confidence: high)</sub>

### Repositories list
Manage configured repositories: enable/disable, reorder, add new, edit details

**Shows:** List of repositories with name, address, enabled state, Mirror lists, Drag-and-drop reordering
**Actions:** Enable/disable repository, Reorder repositories, Add new repository, Edit repository details

<sub>inferred from: org.fdroid.ui.navigation.NavigationKey, org.fdroid.ui.utils.DragDropState (confidence: medium)</sub>

### Nearby swap start
Let the user enable Bluetooth or Wi-Fi Direct, see nearby peers, and initiate an app swap session

**Shows:** Bluetooth toggle switch, Current Wi-Fi network name, List of nearby peers with device names, Progress indicator while scanning
**Actions:** Turn Bluetooth swap on/off, Refresh peer list, Select a peer to start swap

<sub>inferred from: org.fdroid.fdroid.nearby.StartSwapView, org.fdroid.fdroid.views.main.NearbyViewBinder (confidence: high)</sub>

### Nearby app selection
Let the user pick installed apps to share with a nearby device via the swap workflow

**Shows:** List of installed apps with checkboxes, Search/filter field
**Actions:** Tap to toggle app selection, Filter list by name

<sub>inferred from: org.fdroid.fdroid.nearby.SelectAppsView (confidence: high)</sub>

### Nearby Swap
Guide the user through discovering nearby devices via Bluetooth and exchanging apps or repositories

**Shows:** Bluetooth permission requests, Device discovery progress, Swap configuration confirmation, Next/back navigation
**Actions:** Enable Bluetooth, Make device discoverable, Confirm swap parameters, Proceed to next step, Cancel swap

<sub>inferred from: org.fdroid.fdroid.nearby.SwapWorkflowActivity (confidence: high)</sub>

### Swap Success
Display apps received from a nearby swap and let the user install them

**Shows:** List of received apps with install state, App icons and metadata, Install buttons
**Actions:** Install received apps, Confirm installation, View app details

<sub>inferred from: org.fdroid.ui.nearby.SwapSuccessViewModel (confidence: high)</sub>

### Panic screen
Provides an emergency exit or privacy feature that can be triggered to quickly hide the app or show a panic dialog

**Shows:** Panic dialog, Settings for panic behavior
**Actions:** Trigger panic mode, Configure panic settings, Handle incoming panic intents

<sub>inferred from: org.fdroid.ui.panic.PanicActivity (confidence: high)</sub>

### Panic settings
Configure panic mode behavior including hiding the app, exiting the app, and resetting repositories

**Shows:** Toggle for hide app, Toggle for exit app, Toggle for reset repos, App icon selector
**Actions:** Enable/disable hide app, Enable/disable exit app, Enable/disable reset repos, Change app icon

<sub>inferred from: org.fdroid.ui.panic.PanicSettingsViewModel (confidence: high)</sub>

## Features

- **Nearby Bluetooth app swap** — Exchange apps and repositories with nearby devices over Bluetooth without internet
- **Crash reporting** — Automatic crash collection and reporting via ACRA
- **Repository management** — Configure and manage multiple app repositories with mirrors, certificates, and priorities
- **App installation management** — Handle installation, update, and uninstallation of apps from repositories
- **Repository index parsing (v1 and v2)** — Parse and serialize F-Droid repository index formats (v1 legacy and v2 current)
- **App metadata storage** — Stores detailed app information including author, links, changelog, license, and localized text/assets
- **Local repo HTTPS certificate management** — Generates and manages a keystore with self-signed certificates for serving a local F-Droid repo over HTTPS during nearby share
- **Panic mode configuration** — Allows user to set actions triggered by panic gesture: hide app from launcher, exit app, wipe repo configuration
- **Drag and drop reordering** — Enables reordering items in a Compose LazyList with animated drag preview and auto-scroll
- **App metadata model** — Represents an app with package name, version codes, install status, and update availability
- **Repository database operations** — CRUD and reordering for configured F-Droid repositories
- **App list UI state** — Holds filtered/sorted app list, categories, anti-features, and filter badges for the main browse screen
- **Index v2 metadata serialization** — Kotlin serialization for repository index v2 fields (name, summary, description, license, source, issue tracker, etc.)
- **Index v2 screenshot model** — Stores screenshots for multiple device form factors (phone, 7-inch, 10-inch, wear, TV)
- **APK file sharing via ContentProvider** — Exposes APK files via a ContentProvider so other apps can send/install APKs shared by F-Droid
- **Nearby app swap tracking** — Models the result of a successful nearby app swap, including package details, version info, compatibility, and install state
- **Resumable file downloader** — Downloads files (indexes, APKs) with support for resume, progress reporting, cancellation, and integrity verification
- **Package version serialization** — Serializes/deserializes PackageVersionV2 objects for index v2 format, including metadata like anti-features, release channels, and signer info
- **App database** — Room database storing app metadata, localized files, and full-text search index for apps across repositories
- **Full-text search** — FTS entity for searching apps by name, summary, description, author, and package name
- **Repository preview before adding** — Displays a list of apps from a repository with details so the user can decide whether to add it
- **Bluetooth HTTP-like request/response protocol** — Implements GET and HEAD request handling over a Bluetooth connection for nearby app exchange
- **Repository manifest V2 serialization** — Serializes and deserializes repository index manifests containing version info, permissions, features, and SDK requirements
- **Updatable app tracking** — Tracks installed apps that have updates available, including version info, repo source, and vulnerability status
- **Onboarding state management** — Persists onboarding visibility state per feature using SharedPreferences, with legacy migration
- **Repository configuration from swap intent** — Parses incoming intents or URIs to extract repository details (host, credentials, fingerprint, Wi-Fi BSSID/SSID) for adding a repo received via nearby share
- **Notification channels and alerts** — Creates dedicated notification channels and shows/cancels notifications for app installs, install success, repo updates, available app updates, and self-updates
- **Flexible download requests** — Models download requests with support for multiple mirrors, proxy configuration, authentication, IPFS CIDs, and integrity verification (SHA256, size)
- **Type-safe navigation** — Provides sealed navigation keys for Discover, Search, MyApps, Repos, AppList, and AppDetails destinations

## Network calls

- `Multiple repository URLs (e.g., https://f-droid.org, https://apt.izzysoft.de/fdroid/repo, https://archive.newpipe.net/fdroid/repo, https://briarproject.org/fdroid/repo, https://guardianproject.info/fdroid/repo, IPFS gateways)` — Fetch repository indexes and app metadata from configured repositories
- `Dynamic (repository URLs and mirror URLs)` — Download APKs, index files, or other assets over HTTP/HTTPS with resume support
- `Bluetooth RFCOMM` — Exchange app metadata and APKs over Bluetooth using a custom HTTP-like protocol

## Data stored

- **Repository configurations** (database) — Repository metadata including name, address, mirrors, description, certificate, version, enabled state, and weight
- **App settings** (preferences) — User preferences managed via SettingsManager
- **Installed apps cache** (cache) — Cache of currently installed apps for compatibility checking and swap operations
- **App and AppMetadata entities** (database) — Room entities holding app package info, metadata (author, website, license, changelog, source code, issue tracker, donation links), and localized files (icons, screenshots, videos)
- **Local repo keystore** (file) — BKS keystore file (kerplapp.bks) containing self-signed certificate and key pair for HTTPS local repo server
- **Panic settings** (preferences) — SharedPreferences flags for hideApp, exitApp, resetRepos, and custom app icon selection
- **Repository list** (database) — Enabled/disabled repositories, their URLs, mirror lists, and display order
- **App index metadata** (database) — Parsed v1/v2 index data including localized strings, screenshots, changelogs, licenses
- **Downloaded file cache** (cache) — Temporary storage for downloaded index files or APKs during download operations
- **APK files for sharing** (file) — APK files exposed via ContentProvider for sending to other apps or installation
- **AppMetadataFts** (database) — Full-text search index: repoId, name, summary, description, authorName, packageName
- **Repository index manifests (V2)** (database) — Parsed manifest data including versionName, versionCode, usesSdk, maxSdkVersion, signer, usesPermission, usesPermissionSdk23, nativecode, features, minSdkVersion, featureNames
- **Onboarding preferences** (preferences) — Boolean flags for each onboarding flow (main, updates, filter, repositories, repo details, app issues, anti-features)
- **LocalizedFileList** (database) — Room entity holding localized metadata for repo files: repoId, packageName, type, locale, name, sha256, size, ipfsCidV1
- **Repository V2 metadata** (database) — Persisted repository configuration including name, icon, address, web URL, description, mirrors, timestamp, categories, release channels, and anti-features
- **Onboarding and settings state** (preferences) — Tracks onboarding completion and user preferences such as metered network warnings

## Permissions, justified by observed behaviour

- `android.permission.CAMERA` — Used by CaptureActivity for QR code scanning (e.g., scanning repository QR codes or app share codes)
- `android.permission.MANAGE_EXTERNAL_STORAGE` — Required for reading/writing APK files and repository indexes to shared storage, and for USB OTG directory picking via OPEN_DOCUMENT_TREE
- `android.permission.REQUEST_INSTALL_PACKAGES` — Allows installation of downloaded APKs from repositories, nearby shares, and local repo server
- `android.permission.QUERY_ALL_PACKAGES` — Needed to query installed apps for compatibility checking, swap operations, and displaying installed app list
- `android.permission.READ_EXTERNAL_STORAGE` — Reads APK files, repository indexes, and keystore from storage (legacy permission, still declared for compatibility)
- `android.permission.WRITE_EXTERNAL_STORAGE` — Writes downloaded APKs, indexes, and keystore to storage (legacy permission, still declared for compatibility)

## Platform dependencies

Android Keystore / BouncyCastle provider for certificate generation, Android POST_NOTIFICATIONS permission (API 33+), Android SharedPreferences, Bluetooth (for nearby sharing and swap), BluetoothAdapter for nearby swap, Camera (for QR code scanning via CaptureActivity), ContentProvider framework (for APK sharing), Coroutines for async download, Kotlinx Serialization, OkHttp (via HttpManager), PackageManager for installed app queries and component enabled state (panic hide/exit), Room database, Storage access (READ/WRITE_EXTERNAL_STORAGE, MANAGE_EXTERNAL_STORAGE), USB OTG support for external storage, Wi-Fi Direct / WifiManager for network peer discovery, android.intent.action.OPEN_DOCUMENT_TREE for directory picking, android.permission.ACCESS_COARSE_LOCATION for nearby discovery, android.settings.MANAGE_APP_ALL_FILES_ACCESS_PERMISSION for scoped storage, WorkManager, ACRA, Glide

## Caveats

- Actual repository URLs and download triggers are not in these classes
- AppDetailsItem parent class not provided, so some fields inferred
- AppDetailsViewModel references many injected dependencies (RepoManager, UpdateChecker, etc.) whose implementations are not provided
- AppListModel is a UI state holder; the actual app list rendering and repository browsing screens are not in this part
- AppListViewModel references AppListType and RepoManager but their implementations are not in this part
- AppV1 serializer indicates legacy index format support but not whether v1 repos are still used
- Database schema for repositories not fully shown
- DownloadRequest is a data model; the actual HTTP/IPFS download execution code is not in this class
- Downloader's specific network endpoints are not hardcoded in this class
- DragDropState usage context (which list) not determined from this class alone
- Entry$$serializer is compiler-generated; the Entry data class itself not provided
- Exact UI layout of AddRepoPreviewScreen not fully known (only Compose component names and string literals)
- Full swap workflow steps beyond the activity and viewmodel not visible
- HttpDownloader's exact usage contexts (repo index vs APK) not specified in this snippet
- Integration between nearby Bluetooth protocol and the ContentProvider is inferred but not fully traced
- MainActivity body is truncated; exact UI composition not visible
- NavigationKey only defines keys; the navigation graph and fragment/activity destinations are not shown
- Network call details inferred from string literals in static analysis, not directly from these 6 classes
- Network endpoints from strings list not directly referenced in these six classes
- NewRepoConfig references SwapWorkflowActivity.EXTRA_PREVENT_FURTHER_SWAP_REQUESTS but that activity not in this part
- No network endpoints directly invoked in these classes
- NotificationManager uses NotificationManagerCompat but actual notification content templates not shown
- Only the StartSwapView UI class is shown; the actual swap transfer logic resides in SwapService and related classes not included here
- PackageVersionV2 serializer is for Kotlin serialization; actual parsing logic elsewhere
- PanicActivity's exact UI and trigger mechanism not fully visible from decompiled snippet
- PanicSettingsViewModel references OnboardingManager and AppIconManager but their implementations not shown
- PreviewUtilsKt only shows test constants; production preview logic not shown
- SelectAppsView extends SwapView but SwapView implementation not provided; exact swap transport unknown
- Serializer classes are compiler-generated; the actual data classes are not included
- Serializers are compiler-generated; the actual index download and parsing flow is not visible
- SwapSuccessItem is a model only; the swap UI/flow is in other classes not provided
- The actual Nearby discovery protocol implementation (Bluetooth/Wi-Fi Direct) is not shown in NearbyViewBinder; only the UI binding and permission handling
- UI screens for onboarding not shown in these classes; only the state manager is present
