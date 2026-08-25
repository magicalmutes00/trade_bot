package com.bofedge.app.di

import android.content.Context
import com.bofedge.app.BuildConfig
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Named

@Module
@InstallIn(SingletonComponent::class)
object AppModule {

    /** OAuth Web client ID from Firebase console (see gradle.properties). */
    @Provides
    @Named("firebaseWebClientId")
    fun provideFirebaseWebClientId(): String = BuildConfig.FIREBASE_WEB_CLIENT_ID

    @Provides
    @Named("appContext")
    fun provideAppContext(@ApplicationContext context: Context): Context = context
}
