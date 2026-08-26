package com.bofedge.app

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AccountCircle
import androidx.compose.material.icons.filled.Grid4x4
import androidx.compose.material.icons.filled.Logout
import androidx.compose.material.icons.filled.QueryStats
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Star
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.bofedge.core.ui.components.EmptyState
import com.bofedge.domain.model.AuthUser
import com.bofedge.feature.auth.presentation.AuthViewModel
import com.bofedge.feature.heatmap.presentation.HeatmapRoute
import com.bofedge.feature.watchlist.presentation.WatchlistRoute
import com.bofedge.feature.instrument.presentation.FullscreenChartScreen
import com.bofedge.feature.instrument.presentation.InstrumentDetailRoute
import com.bofedge.feature.scanner.presentation.ScannerRoute
import com.bofedge.navigation.Routes

private data class Tab(
    val route: String,
    val label: String,
    val icon: androidx.compose.ui.graphics.vector.ImageVector,
    val enabled: Boolean = true,
)

private val TABS = listOf(
    Tab(Routes.DASHBOARD, "Dashboard", Icons.Filled.QueryStats),
    Tab(Routes.SCANNER, "Scanner", Icons.Filled.Search),
    Tab(Routes.HEATMAP, "Heatmap", Icons.Filled.Grid4x4),
    Tab(Routes.WATCHLIST, "Watchlist", Icons.Filled.Star),
    Tab(Routes.PROFILE, "Profile", Icons.Filled.AccountCircle),
)

/**
 * Authenticated shell: bottom navigation + nested NavHost.
 * Only reachable while auth state is Authenticated; logout flips that state
 * and this screen is replaced by Login automatically.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MainShell(user: AuthUser) {
    val context = LocalContext.current
    val authViewModel: AuthViewModel = hiltViewModel()
    val mainViewModel: MainViewModel = hiltViewModel()
    val navController = rememberNavController()
    val backStackEntry by navController.currentBackStackEntryAsState()
    val currentRoute = backStackEntry?.destination?.route

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("BOF Edge", fontWeight = FontWeight.SemiBold) },
            )
        },
        bottomBar = {
            NavigationBar {
                TABS.forEach { tab ->
                    NavigationBarItem(
                        selected = currentRoute == tab.route,
                        enabled = tab.enabled,
                        onClick = {
                            navController.navigate(tab.route) {
                                popUpTo(navController.graph.findStartDestination().id) { saveState = true }
                                launchSingleTop = true
                                restoreState = true
                            }
                        },
                        icon = { Icon(tab.icon, contentDescription = tab.label) },
                        label = { Text(tab.label) },
                    )
                }
            }
        },
    ) { padding ->
        NavHost(
            navController = navController,
            startDestination = Routes.DASHBOARD,
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
            enterTransition = {
                androidx.compose.animation.fadeIn(androidx.compose.animation.core.tween(220)) +
                    androidx.compose.animation.slideInHorizontally(
                        androidx.compose.animation.core.tween(260)) { it / 6 }
            },
            exitTransition = {
                androidx.compose.animation.fadeOut(androidx.compose.animation.core.tween(180))
            },
            popEnterTransition = {
                androidx.compose.animation.fadeIn(androidx.compose.animation.core.tween(220))
            },
            popExitTransition = {
                androidx.compose.animation.fadeOut(androidx.compose.animation.core.tween(180)) +
                    androidx.compose.animation.slideOutHorizontally(
                        androidx.compose.animation.core.tween(240)) { it / 6 }
            },
        ) {
            composable(Routes.DASHBOARD) {
                val realtimeViewModel: RealtimeViewModel = hiltViewModel()
                DashboardTab(mainViewModel = mainViewModel, realtimeViewModel = realtimeViewModel)
            }
            composable(Routes.SCANNER) {
                ScannerRoute(
                    onOpenInstrument = { id -> navController.navigate(Routes.instrumentDetails(id)) },
                    viewModel = hiltViewModel(),
                )
            }
            composable(Routes.INSTRUMENT_DETAILS) {
                InstrumentDetailRoute(
                    onOpenFullscreen = { id, symbol ->
                        navController.navigate(Routes.fullscreenChart(id, symbol))
                    },
                    viewModel = hiltViewModel(),
                )
            }
            composable(Routes.FULLSCREEN_CHART) { backStackEntry ->
                FullscreenChartScreen(viewModel = hiltViewModel())
            }
            composable(Routes.HEATMAP) {
                val vm: com.bofedge.feature.heatmap.presentation.HeatmapViewModel = hiltViewModel()
                HeatmapRoute(
                    onOpenInstrument = { id -> navController.navigate(Routes.instrumentDetails(id)) },
                    viewModel = vm,
                )
            }
            composable(Routes.WATCHLIST) {
                val vm: com.bofedge.feature.watchlist.presentation.WatchlistViewModel = hiltViewModel()
                WatchlistRoute(
                    onOpenInstrument = { id -> navController.navigate(Routes.instrumentDetails(id)) },
                    viewModel = vm,
                )
            }
            composable(Routes.PROFILE) {
                val prefsVm: NotificationPrefsViewModel = hiltViewModel()
                ProfileTab(
                    mainViewModel = mainViewModel,
                    prefsViewModel = prefsVm,
                    authViewModel = authViewModel,
                )
            }
        }
    }
}




