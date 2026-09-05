plugins {
    alias(libs.plugins.android.library)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.ksp)
    alias(libs.plugins.hilt)
}

android {
    namespace = "com.bofedge.data"
    compileSdk = 34

    defaultConfig {
        minSdk = 26
        consumerProguardFiles("consumer-rules.pro")
    }

    buildTypes {
        // API origin is configurable from gradle.properties so debug/release
        // can independently target local dev or the production backend.
        debug {
            buildConfigField(
                "String",
                "BOF_BASE_URL",
                "\"https://ab4347fe9b0236.lhr.life/api/v1/\""
            )
        }
        release {
            buildConfigField(
                "String",
                "BOF_BASE_URL",
                "\"https://ab4347fe9b0236.lhr.life/api/v1/\""
            )
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
        buildConfig = true
    }
}

dependencies {
    implementation(project(":domain"))

    implementation(libs.androidx.core.ktx)
    implementation(libs.kotlinx.coroutines.android)
    implementation(libs.kotlinx.coroutines.play.services)

    // Networking
    api(libs.retrofit)
    implementation(libs.retrofit.kotlinx.serialization)
    implementation(libs.okhttp)
    implementation(libs.okhttp.logging)
    implementation(libs.kotlinx.serialization.json)

    // Firebase (token management for the auth interceptor)
    api(platform(libs.firebase.bom))
    api(libs.firebase.auth)

    // DI
    implementation(libs.hilt.android)
    ksp(libs.hilt.compiler)

    testImplementation(libs.junit)
}
