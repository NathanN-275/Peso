package expo.modules.pesoprivateexport

import android.net.Uri
import android.system.ErrnoException
import android.system.Os
import android.system.OsConstants
import expo.modules.kotlin.Promise
import expo.modules.kotlin.exception.CodedException
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition
import okhttp3.Authenticator
import okhttp3.Call
import okhttp3.Callback
import okhttp3.ConnectionPool
import okhttp3.CookieJar
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import java.io.File
import java.io.IOException
import java.net.URI
import java.util.Locale
import java.util.UUID
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

private const val CACHE_NAME = "peso-private-export-v1"
private const val ERROR_CODE = "ERR_PESO_PRIVATE_EXPORT"
private const val ERROR_MESSAGE = "Unable to save this private export. Try again."
private const val UUID_PATTERN = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
private const val NIL_UUID = "00000000-0000-0000-0000-000000000000"
private val uuid = Regex(UUID_PATTERN)
private val bytePath = Regex("/private-media/video/($UUID_PATTERN)/export%3A(?:clean|pose|barbell|pose-barbell)")
private val mediaGrant = Regex("[A-Za-z0-9_-]{42}[AEIMQUYcgkosw048]")
private val positiveLength = Regex("[1-9][0-9]{0,18}")
private val extensions = mapOf(
  "video/mp4" to "mp4",
  "video/quicktime" to "mov",
  "video/x-m4v" to "m4v",
  "video/m4v" to "m4v",
  "video/webm" to "webm",
  "video/x-matroska" to "mkv"
)
private val assetNames = extensions.values.map { "asset.$it" }.toSet()

class PesoPrivateExportModule : Module() {
  private val owner = Any()
  private var destroyed = false
  private var purged = false

  override fun definition() = ModuleDefinition {
    Name("PesoPrivateExport")

    Function("purgeOnStartup") { -> safely { purgeOnStartup() } }
    Function("reserve") { -> safely { reserve() } }
    Function("cancel") { id: String -> safely { cancel(id) } }
    Function("remove") { id: String -> safely { remove(id) } }
    AsyncFunction("download") { id: String, url: String, grant: String, promise: Promise ->
      safely { download(id, url, grant, promise) }
    }
    OnDestroy { abandon() }
  }

  private fun cacheRoot() = File(appContext.cacheDirectory.canonicalFile, CACHE_NAME)

  private fun purgeOnStartup() = synchronized(lock) {
    check(!destroyed)
    if (purged) return@synchronized
    active?.let { previous ->
      check(previous.abandoned && previous.call == null)
      removeDirectory(previous.directory)
      active = null
    }
    val root = cacheRoot()
    if (directoryExists(root)) {
      for (directory in checkNotNull(root.listFiles())) {
        check(uuid.matches(directory.name) && directory.name != NIL_UUID)
        removeDirectory(directory)
      }
    }
    purged = true
  }

  private fun reserve(): String = synchronized(lock) {
    check(purged && !destroyed && active == null)
    val root = cacheRoot()
    if (!directoryExists(root)) check(root.mkdir())
    val id = UUID.randomUUID().toString()
    val directory = File(root, id)
    check(directory.mkdir())
    active = Reservation(owner, id, directory)
    id
  }

  private fun cancel(id: String) {
    val call = synchronized(lock) {
      val reservation = owned(id) ?: return
      reservation.canceled = true
      reservation.call
    }
    call?.cancel()
  }

  private fun remove(id: String) = synchronized(lock) {
    val reservation = owned(id) ?: return@synchronized
    // The promise settles only after the response and output stream close.
    check(reservation.call == null)
    removeDirectory(reservation.directory)
    active = null
  }

  private fun abandon() {
    val call = synchronized(lock) {
      destroyed = true
      val reservation = active?.takeIf { it.owner === owner } ?: return
      reservation.canceled = true
      reservation.abandoned = true
      if (reservation.call == null) clearAbandoned(reservation)
      reservation.call
    }
    call?.cancel()
  }

  private fun owned(id: String) = active?.takeIf { it.owner === owner && it.id == id }

  private fun download(id: String, url: String, grant: String, promise: Promise) {
    val request = request(url, grant)
    val call = client.newCall(request)
    val reservation = synchronized(lock) {
      check(!destroyed)
      val entry = checkNotNull(owned(id))
      check(!entry.canceled && !entry.started)
      entry.started = true
      entry.call = call
      entry
    }
    try {
      call.enqueue(object : Callback {
        override fun onFailure(call: Call, e: IOException) {
          settle(reservation, null, promise)
        }

        override fun onResponse(call: Call, response: Response) {
          val file = try {
            response.use { copyAsset(call, it, reservation.directory) }
          } catch (_: Exception) {
            null
          }
          settle(reservation, file, promise)
        }
      })
    } catch (_: Exception) {
      settle(reservation, null, promise)
    }
  }

  private fun settle(reservation: Reservation, file: File?, promise: Promise) = synchronized(lock) {
    if (active !== reservation || reservation.call == null) return@synchronized
    reservation.call = null
    if (reservation.abandoned) {
      clearAbandoned(reservation)
      return@synchronized
    }
    if (file == null || reservation.canceled) {
      promise.reject(ERROR_CODE, ERROR_MESSAGE, null)
    } else {
      promise.resolve(Uri.fromFile(file).toString())
    }
  }

  private fun clearAbandoned(reservation: Reservation) {
    try {
      removeDirectory(reservation.directory)
      active = null
    } catch (_: Exception) {
      // Retain the abandoned reservation so the next startup can retry cleanup.
    }
  }

  private class Reservation(val owner: Any, val id: String, val directory: File) {
    var canceled = false
    var abandoned = false
    var started = false
    var call: Call? = null
  }

  private companion object {
    val lock = Any()
    var active: Reservation? = null
    val client: OkHttpClient = OkHttpClient.Builder()
      .followRedirects(false)
      .followSslRedirects(false)
      .retryOnConnectionFailure(false)
      .authenticator(Authenticator.NONE)
      .proxyAuthenticator(Authenticator.NONE)
      .cookieJar(CookieJar.NO_COOKIES)
      .cache(null)
      .connectionPool(ConnectionPool(0, 1, TimeUnit.SECONDS))
      .callTimeout(135, TimeUnit.SECONDS)
      .connectTimeout(10, TimeUnit.SECONDS)
      .readTimeout(20, TimeUnit.SECONDS)
      .addNetworkInterceptor { chain ->
        // Some HTTP follow-ups are independent of retryOnConnectionFailure.
        val request = chain.request()
        val sent = request.tag(AtomicBoolean::class.java)
        if (sent == null || !sent.compareAndSet(false, true)) throw IOException(ERROR_MESSAGE)
        chain.proceed(request)
      }
      .build()
  }
}

private fun request(url: String, grant: String): Request {
  check(mediaGrant.matches(grant))
  val parsed = URI(url)
  val host = checkNotNull(parsed.host)
  check(parsed.scheme == "https" && (host == "usepeso.com" || host.endsWith(".usepeso.com")))
  check(parsed.rawAuthority == host || parsed.rawAuthority == "$host:443")
  check(parsed.rawQuery == null && parsed.rawFragment == null && parsed.rawUserInfo == null)
  val match = checkNotNull(bytePath.matchEntire(parsed.rawPath))
  check(match.groupValues[1] != NIL_UUID)
  return Request.Builder()
    .url(url)
    .header("X-Peso-Media-Grant", grant)
    .header("Cache-Control", "no-store")
    .header("Accept-Encoding", "identity")
    .tag(AtomicBoolean::class.java, AtomicBoolean())
    .build()
}

private fun copyAsset(call: Call, response: Response, directory: File): File {
  check(response.code == 200 && !call.isCanceled())
  val headers = response.headers
  val cache = headers.values("Cache-Control").flatMap { it.split(',') }
    .map { it.trim().lowercase(Locale.ROOT) }
  check("private" in cache && "no-store" in cache)
  val encoding = headers.values("Content-Encoding")
  check(encoding.isEmpty() || encoding.singleOrNull()?.trim()?.lowercase(Locale.ROOT) == "identity")
  check(headers.values("Transfer-Encoding").isEmpty() && headers.values("Content-Range").isEmpty())
  val mediaType = headers.values("Content-Type").singleOrNull()?.trim()?.lowercase(Locale.ROOT)
  val extension = checkNotNull(extensions[mediaType])
  val lengthHeader = checkNotNull(headers.values("Content-Length").singleOrNull())
  check(positiveLength.matches(lengthHeader))
  val expected = checkNotNull(lengthHeader.toLongOrNull())
  val body = checkNotNull(response.body)
  check(body.contentLength() == expected)

  check(directoryExists(directory) && directory.usableSpace >= expected)
  val file = File(directory, "asset.$extension")
  check(file.createNewFile())
  var written = 0L
  body.byteStream().use { input ->
    file.outputStream().use { output ->
      val buffer = ByteArray(64 * 1024)
      while (true) {
        check(!call.isCanceled())
        val count = input.read(buffer)
        if (count == -1) break
        check(!call.isCanceled() && count > 0 && count <= expected - written)
        output.write(buffer, 0, count)
        written += count
      }
    }
  }
  check(!call.isCanceled() && written == expected && file.length() == expected)
  return file
}

private fun fileMode(file: File): Int? = try {
  Os.lstat(file.path).st_mode
} catch (error: ErrnoException) {
  // A stat error cannot prove a cache entry disappeared.
  if (error.errno == OsConstants.ENOENT) null else throw error
}

private fun directoryExists(directory: File): Boolean {
  val mode = fileMode(directory) ?: return false
  check(OsConstants.S_ISDIR(mode) && directory.canonicalFile == directory.absoluteFile)
  return true
}

private fun removeDirectory(directory: File) {
  if (!directoryExists(directory)) return
  for (file in checkNotNull(directory.listFiles())) {
    val mode = fileMode(file) ?: continue
    check(file.name in assetNames && OsConstants.S_ISREG(mode))
    check(file.delete() || fileMode(file) == null)
  }
  check(directory.delete() || fileMode(directory) == null)
}

private fun <T> safely(action: () -> T): T = try {
  action()
} catch (_: Exception) {
  throw CodedException(ERROR_CODE, ERROR_MESSAGE, null)
}
