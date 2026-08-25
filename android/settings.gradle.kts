pluginManagement {
    repositories {
        google {
            content {
                includeGroupByRegex("com\\.android.*")
                includeGroupByRegex("com\\.google.*")
                includeGroupByRegex("androidx.*")
            }
        }
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "BOFEdge"

include(":app")
include(":core")
include(":data")
include(":domain")
include(":navigation")
include(":feature:auth")
include(":feature:scanner")
include(":feature:instrument")
include(":feature:heatmap")
include(":feature:watchlist")


