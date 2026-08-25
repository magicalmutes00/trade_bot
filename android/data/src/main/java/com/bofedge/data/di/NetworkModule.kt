package com.bofedge.data.di

import com.bofedge.data.network.FirebaseAuthInterceptor
import com.bofedge.data.remote.BofApi
import com.bofedge.data.repository.InstrumentRepositoryImpl
import com.bofedge.data.repository.NotificationRepositoryImpl
import com.bofedge.data.repository.WatchlistRepositoryImpl
import com.bofedge.data.repository.UserRepositoryImpl
import com.bofedge.domain.repository.InstrumentRepository
import com.bofedge.domain.repository.NotificationRepository
import com.bofedge.domain.repository.WatchlistRepository
import com.bofedge.domain.repository.UserRepository
import com.google.firebase.auth.FirebaseAuth
import dagger.Binds
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
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
    fun provideOkHttp(firebaseAuth: FirebaseAuth?): OkHttpClient {
        val logging = HttpLoggingInterceptor().apply {
            level = HttpLoggingInterceptor.Level.BASIC // request line only â€” never headers/bodies/tokens
        }
        return OkHttpClient.Builder()
            .addInterceptor(FirebaseAuthInterceptor(firebaseAuth))
            .addInterceptor(logging)
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
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


