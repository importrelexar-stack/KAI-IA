// KAI AI — Android.
// :core  -> Kotlin puro (protocolo con KAI Core, vinculación, SSE, WAV). Se compila y prueba en cualquier JDK 17+.
// :app   -> app Android (Jetpack Compose). Requiere el Android SDK (ANDROID_HOME o local.properties).
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

val hasAndroidSdk = System.getenv("ANDROID_HOME") != null || System.getenv("ANDROID_SDK_ROOT") != null ||
    file("local.properties").let { it.exists() && it.readText().contains("sdk.dir") }

dependencyResolutionManagement {
    repositories {
        if (hasAndroidSdk) google()
        mavenCentral()
    }
}

rootProject.name = "kai-android"
include(":core")
if (hasAndroidSdk) include(":app") else println("KAI: sin Android SDK; se compila sólo :core")
