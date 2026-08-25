plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.ksp)
    alias(libs.plugins.hilt)
}

// ---------------------------------------------------------------------------
// google-services.json is required for Firebase at RUNTIME but must never be
// committed. The plugin is applied only when the developer has placed the
// file, so the project still compiles on a clean checkout.
// ---------------------------------------------------------------------------
val googleServicesFile = file("google-services.json")
if (googleServicesFile.exists()) {
    apply(plugin = "com.google.gms.google-services")
} else {
    logger.warn(
        "google-services.json is missing in /android/app — Firebase will not be " +
            "initialized at runtime. See docs/firebase-setup.md."
    )
}

// ---------------------------------------------------------------------------
// OAuth Web client ID resolution (used by Credential Manager Google Sign-In):
//   1) explicit gradle property  BOF_FIREBASE_WEB_CLIENT_ID  (wins if set)
//   2) fallback: the type-3 oauth client inside google-services.json
// ---------------------------------------------------------------------------
val resolvedWebClientId: String by lazy {
    val fromProperty = (project.findProperty("BOF_FIREBASE_WEB_CLIENT_ID") as? String)?.trim() ?: ""
    if (fromProperty.isNotEmpty()) return@lazy fromProperty
    if (!googleServicesFile.exists()) return@lazy ""
    runCatching {
        val json = groovy.json.JsonSlurper().parse(googleServicesFile) as Map<*, *>
        val clients = (json["client"] as? List<Map<*, *>>).orEmpty()
        val webClient = clients.firstNotNullOfOrNull { c ->
            (c["oauth_client"] as? List<Map<*, *>>).orEmpty()
                .firstOrNull { it["client_type"] == 3 }
        }
        webClient?.get("client_id") as? String ?: ""
    }.getOrDefault("")
}

android {
    namespace = "com.bofedge.app"
    compileSdk = 34

    defaultConfig {
        // Must match the package name registered in Firebase Console
        // (project bofedge-f72ae -> com.trisentric.bofedge).
        applicationId = "com.trisentric.bofedge"
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "0.1.0"

        // App name single source of truth (gradle.properties -> BOF_APP_NAME).
        resValue("string", "app_name", project.findProperty("BOF_APP_NAME") as? String ?: "BOF Edge")

        buildConfigField(
            "String",
            "FIREBASE_WEB_CLIENT_ID",
            "\"$resolvedWebClientId\""
        )
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
}

dependencies {
    implementation(project(":core"))
    implementation(project(":domain"))
    implementation(project(":data"))
    implementation(project(":navigation"))
    implementation(project(":feature:auth"))
    implementation(project(":feature:scanner"))
    implementation(project(":feature:instrument"))
    implementation(project(":feature:heatmap"))
    implementation(project(":feature:watchlist"))

    val composeBom = platform(libs.compose.bom)
    implementation(composeBom)

    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.navigation.compose)

    implementation(libs.compose.ui)
    implementation(libs.compose.material3)
    implementation(libs.compose.material.icons.extended)
    implementation(libs.compose.ui.tooling.preview)
    debugImplementation(libs.compose.ui.tooling)

    implementation(platform(libs.firebase.bom))
    implementation(libs.firebase.auth)
    implementation(libs.firebase.messaging)

    implementation(libs.kotlinx.coroutines.android)

    implementation(libs.hilt.android)
    ksp(libs.hilt.compiler)
    implementation(libs.hilt.navigation.compose)

    testImplementation(libs.junit)
}
