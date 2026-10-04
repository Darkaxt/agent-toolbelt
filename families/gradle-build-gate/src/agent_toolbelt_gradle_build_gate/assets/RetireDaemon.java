import java.io.File;
import java.time.Instant;
import java.util.UUID;
import java.util.function.Consumer;
import org.gradle.cache.FileLockReleasedSignal;
import org.gradle.cache.internal.DefaultFileLockManager;
import org.gradle.cache.internal.ProcessMetaDataProvider;
import org.gradle.cache.internal.locklistener.FileLockContentionHandler;
import org.gradle.internal.remote.internal.RemoteConnection;
import org.gradle.internal.remote.internal.inet.TcpOutgoingConnector;
import org.gradle.internal.serialize.Serializers;
import org.gradle.launcher.daemon.protocol.*;
import org.gradle.launcher.daemon.registry.*;
import org.gradle.launcher.daemon.server.api.DaemonState;
import org.gradle.tooling.internal.provider.action.BuildActionSerializer;

// Uses the target distribution's serializers and authenticated daemon registry.
// Never constructs Stop: StopWhenIdle preserves a build racing our inspection.
class RetireDaemon {
    static PersistentDaemonRegistry registry(File file) {
        if (!file.isFile()) throw new IllegalStateException("Missing registry");
        ProcessMetaDataProvider metadata = new ProcessMetaDataProvider() {
            public String getProcessIdentifier() { return Long.toString(ProcessHandle.current().pid()); }
            public String getProcessDisplayName() { return "Gradle gate retirement"; }
        };
        FileLockContentionHandler contention = new FileLockContentionHandler() {
            public void start(long id, Consumer<FileLockReleasedSignal> action) {}
            public void stop(long id) {}
            public int reservePort() { return -1; }
            public boolean maybePingOwner(int port, long id, String name, long elapsed, FileLockReleasedSignal signal) { return false; }
            public boolean isRunning() { return false; }
        };
        return new PersistentDaemonRegistry(file, new DefaultFileLockManager(metadata, contention),
            (path, mode) -> { throw new IllegalStateException("Registry creation forbidden"); });
    }

    public static void main(String[] args) {
        try {
            boolean inspect = args[0].equals("inspect");
            long pid = Long.parseLong(args[2]);
            long created = Long.parseLong(args[3]);
            ProcessHandle process = ProcessHandle.of(pid).orElse(null);
            if (process == null) { System.out.println("already_exited"); return; }
            Instant start = process.info().startInstant().orElseThrow();
            if (Math.abs(start.toEpochMilli() - created) > 1) throw new IllegalStateException("PID identity changed");
            DaemonInfo target = registry(new File(args[1])).getAll().stream()
                .filter(info -> info.getPid() != null && info.getPid() == pid).findFirst().orElseThrow();
            if (target.getState() != DaemonState.Idle) throw new IllegalStateException("Daemon no longer idle");
            if (!target.getContext().getJavaHome().getCanonicalFile().equals(new File(System.getProperty("java.home")).getCanonicalFile()))
                throw new IllegalStateException("Unexpected target JVM");
            if (inspect) { System.out.println("registry_idle_verified"); return; }
            // Capture exit completion before requesting shutdown; no PID-only polling.
            var exited = process.onExit();
            RemoteConnection<Message> connection = new TcpOutgoingConnector().connect(target.getAddress())
                .create(Serializers.stateful(DaemonMessageSerializer.create(BuildActionSerializer.create())));
            try {
                connection.dispatch(new StopWhenIdle(UUID.randomUUID(), target.getToken()));
                connection.flush();
                Message reply = connection.receive();
                if (!(reply instanceof Result) || reply instanceof Failure) throw new IllegalStateException("Shutdown rejected");
                connection.dispatch(new Finished());
                connection.flush();
            } finally { connection.stop(); }
            exited.get();
            System.out.println("process_exit_verified");
        } catch (Throwable error) {
            // Registry objects and exception messages can contain authentication data.
            System.err.println("Retirement blocked: " + error.getClass().getSimpleName());
            System.exit(2);
        }
    }
}
