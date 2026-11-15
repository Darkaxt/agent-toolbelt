// On-device documents-provider client for agent-toolbelt adb-saf.
//
// The `content` shell command can query and read documents, but its `call`
// extras cannot carry a Uri, so DocumentsContract create/rename/delete are
// unreachable through it. This client runs as the ADB shell user through
// app_process and calls the provider exactly as `content` does (an external
// provider reference from ActivityManager), passing real Uri extras. It never
// gains privileges beyond the calling user; providers that refuse that user
// still refuse.
//
// Usage: CLASSPATH=<dex> app_process / SafClient <base64 JSON request>
// Prints one JSON object. Exit status 0 when "ok" is true.
import android.net.Uri;
import android.os.Binder;
import android.os.Build;
import android.os.Bundle;
import android.os.IBinder;
import android.os.ParcelFileDescriptor;
import android.os.Parcelable;
import android.util.Base64;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import org.json.JSONObject;

public final class SafClient {
    private static final int ROOT_UID = 0;
    private static final int SHELL_UID = 2000;

    public static void main(String[] args) {
        JSONObject result = new JSONObject();
        int status = 1;
        try {
            if (args.length != 1) throw new IllegalArgumentException("Expected one base64 JSON request");
            JSONObject request = new JSONObject(new String(Base64.decode(args[0], Base64.DEFAULT), StandardCharsets.UTF_8));
            result = run(request);
            status = 0;
        } catch (Throwable error) {
            Throwable cause = error instanceof InvocationTargetException ? error.getCause() : error;
            try {
                result.put("ok", false);
                result.put("error_class", cause.getClass().getName());
                result.put("message", String.valueOf(cause.getMessage()));
            } catch (Exception ignored) { }
        }
        System.out.println(result.toString());
        System.exit(status);
    }

    private static JSONObject run(JSONObject request) throws Throwable {
        String op = request.getString("op");
        String authority = request.getString("authority");
        int user = request.optInt("user", 0);
        Provider provider = Provider.acquire(authority, user);
        try {
            JSONObject result = new JSONObject();
            result.put("ok", true);
            result.put("op", op);
            if (op.equals("create")) {
                Bundle extras = new Bundle();
                extras.putParcelable("uri", documentUri(authority, request.getString("parent_id")));
                extras.putString("mime_type", request.getString("mime_type"));
                extras.putString("_display_name", request.getString("display_name"));
                Bundle out = provider.call("android:createDocument", extras);
                result.put("document_id", returnedId(out));
            } else if (op.equals("rename")) {
                Bundle extras = new Bundle();
                extras.putParcelable("uri", documentUri(authority, request.getString("document_id")));
                extras.putString("_display_name", request.getString("display_name"));
                Bundle out = provider.call("android:renameDocument", extras);
                String renamed = returnedId(out);
                result.put("document_id", renamed == null ? request.getString("document_id") : renamed);
            } else if (op.equals("delete")) {
                Bundle extras = new Bundle();
                extras.putParcelable("uri", documentUri(authority, request.getString("document_id")));
                provider.call("android:deleteDocument", extras);
            } else if (op.equals("write")) {
                // "wt": truncate. Plain "w" does not truncate on several providers,
                // which would leave stale trailing bytes after a shorter overwrite.
                Uri uri = documentUri(authority, request.getString("document_id"));
                ParcelFileDescriptor descriptor = provider.openFile(uri, "wt");
                if (descriptor == null) throw new IllegalStateException("Provider returned no descriptor");
                MessageDigest digest = MessageDigest.getInstance("SHA-256");
                long written = 0;
                try (InputStream input = new FileInputStream(request.getString("source"));
                     OutputStream output = new FileOutputStream(descriptor.getFileDescriptor())) {
                    byte[] buffer = new byte[65536];
                    int count;
                    while ((count = input.read(buffer)) > 0) {
                        output.write(buffer, 0, count);
                        digest.update(buffer, 0, count);
                        written += count;
                    }
                    output.flush();
                    descriptor.getFileDescriptor().sync();
                } finally {
                    descriptor.close();
                }
                result.put("bytes_written", written);
                result.put("sha256", hex(digest.digest()));
            } else {
                throw new IllegalArgumentException("Unknown op " + op);
            }
            return result;
        } finally {
            provider.release();
        }
    }

    private static Uri documentUri(String authority, String documentId) {
        return new Uri.Builder().scheme("content").authority(authority)
            .appendPath("document").appendPath(documentId).build();
    }

    private static String returnedId(Bundle out) {
        if (out == null) return null;
        Parcelable value = out.getParcelable("uri");
        if (!(value instanceof Uri)) return null;
        java.util.List<String> segments = ((Uri) value).getPathSegments();
        return segments.size() >= 2 ? segments.get(1) : null;
    }

    private static String hex(byte[] bytes) {
        StringBuilder text = new StringBuilder();
        for (byte b : bytes) text.append(String.format("%02x", b));
        return text.toString();
    }

    // The hidden IContentProvider binder interface; its call/openFile signatures
    // changed in Android 10 (29), 11 (30) and 12 (31).
    private static final class Provider {
        final Object activityManager;
        final Object binder;
        final IBinder token;
        final String authority;
        final int user;

        private Provider(Object activityManager, Object binder, IBinder token, String authority, int user) {
            this.activityManager = activityManager;
            this.binder = binder;
            this.token = token;
            this.authority = authority;
            this.user = user;
        }

        static Provider acquire(String authority, int user) throws Throwable {
            Object am = Class.forName("android.app.ActivityManager").getMethod("getService").invoke(null);
            IBinder token = new Binder();
            Object holder = null;
            for (Method method : am.getClass().getMethods()) {
                if (!method.getName().equals("getContentProviderExternal")) continue;
                Class<?>[] p = method.getParameterTypes();
                if (p.length == 4) holder = method.invoke(am, authority, user, token, "*adb-saf*");
                else if (p.length == 3) holder = method.invoke(am, authority, user, token);
                else continue;
                break;
            }
            if (holder == null) throw new IllegalStateException("Provider not found: " + authority);
            Object binder = holder.getClass().getField("provider").get(holder);
            if (binder == null) throw new IllegalStateException("Provider unavailable: " + authority);
            return new Provider(am, binder, token, authority, user);
        }

        void release() {
            try {
                for (Method method : activityManager.getClass().getMethods()) {
                    String name = method.getName();
                    int count = method.getParameterTypes().length;
                    if (name.equals("removeContentProviderExternalAsUser") && count == 3) {
                        method.invoke(activityManager, authority, token, user);
                        return;
                    }
                    if (name.equals("removeContentProviderExternal") && count == 2) {
                        method.invoke(activityManager, authority, token);
                        return;
                    }
                }
            } catch (Throwable ignored) { }
        }

        static String callingPackage() {
            int uid = android.os.Process.myUid();
            if (uid == ROOT_UID) return "root";
            if (uid == SHELL_UID) return "com.android.shell";
            return null;
        }

        static Object attribution() throws Throwable {
            Class<?> builder = Class.forName("android.content.AttributionSource$Builder");
            Object b = builder.getConstructor(int.class).newInstance(android.os.Process.myUid());
            builder.getMethod("setPackageName", String.class).invoke(b, callingPackage());
            return builder.getMethod("build").invoke(b);
        }

        Bundle call(String method, Bundle extras) throws Throwable {
            for (Method m : binder.getClass().getMethods()) {
                if (!m.getName().equals("call")) continue;
                Class<?>[] p = m.getParameterTypes();
                try {
                    if (Build.VERSION.SDK_INT >= 31 && p.length == 5 && !p[0].equals(String.class)) {
                        return (Bundle) m.invoke(binder, attribution(), authority, method, null, extras);
                    }
                    if (Build.VERSION.SDK_INT == 30 && p.length == 6) {
                        return (Bundle) m.invoke(binder, callingPackage(), null, authority, method, null, extras);
                    }
                    if (Build.VERSION.SDK_INT == 29 && p.length == 5 && p[0].equals(String.class)) {
                        return (Bundle) m.invoke(binder, callingPackage(), authority, method, null, extras);
                    }
                } catch (InvocationTargetException error) {
                    throw error.getCause();
                }
            }
            throw new UnsupportedOperationException("No IContentProvider.call for SDK " + Build.VERSION.SDK_INT);
        }

        ParcelFileDescriptor openFile(Uri uri, String mode) throws Throwable {
            for (Method m : binder.getClass().getMethods()) {
                if (!m.getName().equals("openFile")) continue;
                Class<?>[] p = m.getParameterTypes();
                try {
                    if (Build.VERSION.SDK_INT >= 31 && p.length == 4) {
                        return (ParcelFileDescriptor) m.invoke(binder, attribution(), uri, mode, null);
                    }
                    if (Build.VERSION.SDK_INT == 30 && p.length == 6) {
                        return (ParcelFileDescriptor) m.invoke(binder, callingPackage(), null, uri, mode, null, null);
                    }
                    if (Build.VERSION.SDK_INT == 29 && p.length == 5) {
                        return (ParcelFileDescriptor) m.invoke(binder, callingPackage(), uri, mode, null, null);
                    }
                } catch (InvocationTargetException error) {
                    throw error.getCause();
                }
            }
            throw new UnsupportedOperationException("No IContentProvider.openFile for SDK " + Build.VERSION.SDK_INT);
        }
    }
}
