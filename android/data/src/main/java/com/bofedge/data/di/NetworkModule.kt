package com.bofedge.data.di

import android.content.Context
import com.bofedge.data.network.FirebaseAuthInterceptor
import com.bofedge.data.remote.BofApi
import com.bofedge.data.repository.InstrumentRepositoryImpl
import com.bofedge.data.repository.NotificationRepositoryImpl
import com.bofedge.data.repository.UserRepositoryImpl
import com.bofedge.data.repository.WatchlistRepositoryImpl
import com.bofedge.domain.repository.InstrumentRepository
import com.bofedge.domain.repository.NotificationRepository
import com.bofedge.domain.repository.WatchlistRepository
import com.bofedge.domain.repository.UserRepository
import com.google.firebase.auth.FirebaseAuth
import dagger.Binds
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import kotlinx.serialization.json.Json
import okhttp3.Cache
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import java.io.File
import java.util.concurrent.TimeUnit
import javax.inject.Named
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object NetworkModule {

    @Provides
    @Singleton
    fun provideFirebaseAuth(): FirebaseAuth? = try {
        // null when google-services.json / Firebase config is absent
        FirebaseAuth.getInstance()
    } catch (_: IllegalStateException) {
        null
    }

    @Provides
    @Singleton
    fun provideMarketSocketClient(
        okHttpClient: OkHttpClient,
        json: Json,
        @Named("wsUrl") wsUrl: String,
    ): com.bofedge.data.network.MarketSocketClient =
        com.bofedge.data.network.MarketSocketClient(okHttpClient, json, wsUrl)

    @Provides
    @Singleton
    fun provideJson(): Json = Json {
        ignoreUnknownKeys = true
        explicitNulls = false
        coerceInputValues = true
        isLenient = true // backend Decimal fields arrive as JSON strings
    }

    @Provides
    @Singleton
    fun provideOkHttp(
        @ApplicationContext context: Context,
        firebaseAuth: FirebaseAuth?,
    ): OkHttpClient {
        val logging = HttpLoggingInterceptor().apply {
            level = HttpLoggingInterceptor.Level.BASIC // request line only — never headers/bodies/tokens
        }
        // 10 MB HTTP cache: backend sends Cache-Control: private, max-age=15
        // on public GETs so revisits render instantly and survive brief drops.
        val cache = Cache(File(context.cacheDir, "http_cache"), 10L * 1024 * 1024)
        return OkHttpClient.Builder()
            .cache(cache)
            .addInterceptor(FirebaseAuthInterceptor(firebaseAuth))
            .addInterceptor(com.bofedge.data.network.RetryOnceOnIOException())
            .addInterceptor(logging)
            .connectTimeout(45, TimeUnit.SECONDS)  // tolerates free-tier cold starts
            .readTimeout(60, TimeUnit.SECONDS)
            .writeTimeout(30, TimeUnit.SECONDS)
            .build()
    }

    @Provides
    @Singleton
    fun provideRetrofit(client: OkHttpClient, json: Json): Retrofit =
        Retrofit.Builder()
            .baseUrl(com.bofedge.data.BuildConfig.BOF_BASE_URL)
            .client(client)
            .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
            .build()

    @Provides
    @Singleton
    fun provideBofApi(retrofit: Retrofit): BofApi = retrofit.create(BofApi::class.java)

    @Provides
    @Named("wsUrl")
    fun provideWebSocketUrl(): String =
        com.bofedge.data.BuildConfig.BOF_BASE_URL
            .replace("http", "ws") // ws:// or wss://
            .trimEnd('/') + "/ws/market"
}

@Module
@InstallIn(SingletonComponent::class)
abstract class RepositoryModule {

    @Binds
    abstract fun bindUserRepository(impl: UserRepositoryImpl): UserRepository

    @Binds
    abstract fun bindNotificationRepository(impl: NotificationRepositoryImpl): NotificationRepository

    @Binds
    abstract fun bindWatchlistRepository(impl: WatchlistRepositoryImpl): WatchlistRepository

    @Binds
    abstract fun bindInstrumentRepository(impl: InstrumentRepositoryImpl): InstrumentRepository
}


