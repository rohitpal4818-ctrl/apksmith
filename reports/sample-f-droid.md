# APKSmith report: F-Droid

**Package** `org.fdroid.fdroid` &nbsp;|&nbsp; **Version** 2.0.1 (2000051) &nbsp;|&nbsp; **Risk score** 78/100

- SDK: min 24, target 37
- Main activity: `org.fdroid.IconActivity`
- Size: 12.0MB
- SHA-256: `83d3fe522281c3cb89fce3bc05038f81b3c3b32c108536941f184c5f9bb53778`

## Summary

| Metric | Value |
| --- | --- |
| total classes | 24520 |
| own classes | 3881 |
| third party classes | 20639 |
| third party ratio | 0.8417 |
| total methods | 119203 |
| endpoint count | 44 |
| component count | 36 |
| exported components | 10 |
| native lib count | 1 |
| short name ratio | 0.0035 |

**Findings by severity:** HIGH 6 &nbsp;|&nbsp; MEDIUM 8 &nbsp;|&nbsp; INFO 4

## Findings

| Severity | Finding | Confidence |
| --- | --- | --- |
| **HIGH** | Weak or misused crypto: RC4 | low |
| **HIGH** | Weak or misused crypto: ECB | low |
| **HIGH** | Possible hardcoded encryption key | low |
| **HIGH** | CAMERA declared | high |
| **HIGH** | MANAGE_EXTERNAL_STORAGE declared | high |
| **HIGH** | REQUEST_INSTALL_PACKAGES declared | high |
| **MEDIUM** | Exported activity: org.fdroid.ui.panic.PanicActivity | high |
| **MEDIUM** | Exported activity: org.fdroid.ui.panic.PanicResponderActivity | high |
| **MEDIUM** | Exported activity: org.fdroid.MainActivity | high |
| **MEDIUM** | Weak or misused crypto: MD5 | low |
| **MEDIUM** | 7 endpoint(s) use plain HTTP | high |
| **MEDIUM** | QUERY_ALL_PACKAGES declared | high |
| **MEDIUM** | READ_EXTERNAL_STORAGE declared | high |
| **MEDIUM** | WRITE_EXTERNAL_STORAGE declared | high |
| **INFO** | Exported activity: org.fdroid.IconCalculatorActivity | high |
| **INFO** | Exported activity: org.fdroid.IconActivity | high |
| **INFO** | Exported activity: org.fdroid.fdroid.panic.CalculatorActivity | high |
| **INFO** | 1 native library bundled | high |

## Permissions

| Permission | Severity | Used in code | Why it matters |
| --- | --- | --- | --- |
| `CAMERA` | HIGH | yes | Can take photos and video. |
| `MANAGE_EXTERNAL_STORAGE` | HIGH | no | Full access to all shared storage, bypassing scoped storage. |
| `REQUEST_INSTALL_PACKAGES` | HIGH | no | Can silently ask to install other APKs. |
| `QUERY_ALL_PACKAGES` | MEDIUM | yes | Can enumerate every app installed on the device. |
| `READ_EXTERNAL_STORAGE` | MEDIUM | yes | Reads files on shared storage. |
| `WRITE_EXTERNAL_STORAGE` | MEDIUM | yes | Writes to shared storage. |
| `ACCESS_LOCAL_NETWORK` | LOW | n/a | Declared permission with no specific risk rule. |
| `BLUETOOTH` | LOW | n/a | Declared permission with no specific risk rule. |
| `BLUETOOTH_ADMIN` | LOW | n/a | Declared permission with no specific risk rule. |
| `BLUETOOTH_ADVERTISE` | LOW | n/a | Declared permission with no specific risk rule. |
| `BLUETOOTH_CONNECT` | LOW | n/a | Declared permission with no specific risk rule. |
| `BLUETOOTH_SCAN` | LOW | n/a | Declared permission with no specific risk rule. |
| `CHANGE_NETWORK_STATE` | LOW | n/a | Declared permission with no specific risk rule. |
| `CHANGE_WIFI_MULTICAST_STATE` | LOW | n/a | Declared permission with no specific risk rule. |
| `CHANGE_WIFI_STATE` | LOW | n/a | Declared permission with no specific risk rule. |
| `ENFORCE_UPDATE_OWNERSHIP` | LOW | n/a | Declared permission with no specific risk rule. |
| `FOREGROUND_SERVICE` | LOW | yes | Runs a persistent foreground service. |
| `FOREGROUND_SERVICE_CONNECTED_DEVICE` | LOW | n/a | Declared permission with no specific risk rule. |
| `FOREGROUND_SERVICE_DATA_SYNC` | LOW | n/a | Declared permission with no specific risk rule. |
| `INTERNET` | LOW | yes | Network access. Expected in most apps, worth noting for privacy review. |
| `POST_NOTIFICATIONS` | LOW | n/a | Declared permission with no specific risk rule. |
| `RECEIVE_BOOT_COMPLETED` | LOW | no | Starts automatically on device boot. |
| `REQUEST_DELETE_PACKAGES` | LOW | n/a | Declared permission with no specific risk rule. |
| `UPDATE_PACKAGES_WITHOUT_USER_ACTION` | LOW | n/a | Declared permission with no specific risk rule. |
| `WRITE_SETTINGS` | LOW | n/a | Declared permission with no specific risk rule. |
| `DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION` | LOW | n/a | Declared permission with no specific risk rule. |
| `UPDATE_REPOS` | LOW | n/a | Declared permission with no specific risk rule. |
| `ACCESS_NETWORK_STATE` | INFO | yes | Reads the current network type. |
| `ACCESS_WIFI_STATE` | INFO | yes | Reads WiFi state and scan results. |
| `WAKE_LOCK` | INFO | yes | Keeps the CPU awake. |

## Exported components (10 of 36)

| Kind | Class | Guarded |
| --- | --- | --- |
| activity | `org.fdroid.ui.panic.PanicActivity` | **none** |
| activity | `org.fdroid.ui.panic.PanicResponderActivity` | **none** |
| activity | `org.fdroid.MainActivity` | **none** |
| activity | `org.fdroid.ui.repositories.UpdateRepoActivity` | `org.fdroid.fdroid.permission.UPDATE_REPOS` |
| activity | `org.fdroid.IconCalculatorActivity` | **none** |
| activity | `org.fdroid.IconActivity` | **none** |
| activity | `org.fdroid.fdroid.panic.CalculatorActivity` | **none** |
| service | `androidx.work.impl.background.systemjob.SystemJobService` | `android.permission.BIND_JOB_SERVICE` |
| receiver | `androidx.work.impl.diagnostics.DiagnosticsReceiver` | `android.permission.DUMP` |
| receiver | `androidx.profileinstaller.ProfileInstallReceiver` | `android.permission.DUMP` |

## Endpoints (44)

| URL | Scheme |
| --- | --- |
| `https://4everland.io/ipfs/` | https |
| `https://apt.izzysoft.de/fdroid/repo` | https |
| `https://archive.newpipe.net/fdroid/repo` | https |
| `https://briarproject.org/fdroid/repo` | https |
| `https://f-droid.org` | https |
| `https://f-droid.org/F-Droid.apk` | https |
| `https://f-droid.org/donate` | https |
| `https://f-droid.org/donate/` | https |
| `https://f-droid.org/en/docs/Translation_and_Localization/` | https |
| `https://fdroid.link/#` | https |
| `https://foobar.onion` | https |
| `https://forum.f-droid.org` | https |
| `https://github.com/TeamNewPipe/NewPipe` | https |
| `https://github.com/TeamNewPipe/NewPipe/issues` | https |
| `https://github.com/TeamNewPipe/NewPipe/releases` | https |
| `https://gitlab.com/fdroid/fdroidclient` | https |
| `https://guardianproject.info/fdroid/repo` | https |
| `https://hosted.weblate.org/projects/newpipe/` | https |
| `https://ipfs.io/ipfs/` | https |
| `https://liberapay.com` | https |
| `https://liberapay.com/` | https |
| `https://liberapay.com/F-Droid-Data/donate` | https |
| `https://liberapay.com/TeamNewPipe/donate` | https |
| `http://logback.qos.ch/codes.html` | http |
| `http://logback.qos.ch/codes.html#1andOnly1` | http |
| `http://logback.qos.ch/codes.html#missingRightParenthesis` | http |
| `http://logback.qos.ch/manual/` | http |
| `https://microg.org/fdroid/repo` | https |
| `https://mirror.example.com/fdroid/repo` | https |
| `https://mirror.example.com/foo/bar/fdroid/repo` | https |

## Third-party SDKs

| SDK | Category |
| --- | --- |
| WorkManager | background |
| ACRA | crash-reporting |
| Room | database |
| OkHttp | networking |
| Glide | ui |
