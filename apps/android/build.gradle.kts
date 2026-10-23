// Los plugins se cargan en el classpath raíz: el plugin de Kotlin necesita ver al de Android (AGP).
// AGP sólo se agrega cuando hay Android SDK (así :core se puede compilar sin acceso al repositorio de Google).
buildscript {
    val kotlinVersion = "2.1.0"
    repositories {
        if (rootProject.findProject(":app") != null) google()
        mavenCentral()
        gradlePluginPortal()
    }
    dependencies {
        classpath("org.jetbrains.kotlin:kotlin-gradle-plugin:$kotlinVersion")
        classpath("org.jetbrains.kotlin:kotlin-serialization:$kotlinVersion")
        if (rootProject.findProject(":app") != null) {
            classpath("com.android.tools.build:gradle:8.7.3")
            classpath("org.jetbrains.kotlin:compose-compiler-gradle-plugin:$kotlinVersion")
        }
    }
}
