import java.io.*;
import java.net.*;
import java.nio.channels.*;
import java.util.*;
import java.util.function.Consumer;
import org.gradle.cache.FileLockReleasedSignal;
import org.gradle.cache.internal.DefaultFileLockManager;
import org.gradle.cache.internal.ProcessMetaDataProvider;
import org.gradle.cache.internal.locklistener.FileLockContentionHandler;
import org.gradle.internal.remote.internal.*;
import org.gradle.internal.remote.internal.inet.*;
import org.gradle.internal.serialize.*;
import org.gradle.jvm.toolchain.JavaLanguageVersion;
import org.gradle.internal.nativeintegration.services.NativeServices.NativeServicesMode;
import org.gradle.launcher.daemon.configuration.DaemonPriority;
import org.gradle.launcher.daemon.context.DefaultDaemonContext;
import org.gradle.launcher.daemon.protocol.*;
import org.gradle.launcher.daemon.protocol.Message;
import org.gradle.launcher.daemon.registry.*;
import org.gradle.launcher.daemon.server.api.DaemonState;
import org.gradle.tooling.internal.provider.action.BuildActionSerializer;

// Local protocol fixture, not a Gradle build or reusable daemon.
class SyntheticDaemon {
    public static void main(String[] args) throws Exception {
        long pid = ProcessHandle.current().pid();
        File registry = new File(args[0]);
        try (ServerSocketChannel server = ServerSocketChannel.open()) {
            server.bind(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
            int port = ((InetSocketAddress) server.getLocalAddress()).getPort();
            var address = new MultiChoiceAddress(UUID.randomUUID(), port, List.of(InetAddress.getLoopbackAddress()));
            var context = new DefaultDaemonContext(UUID.randomUUID().toString(), new File(System.getProperty("java.home")),
                JavaLanguageVersion.of(System.getProperty("java.specification.version")), System.getProperty("java.vendor"),
                registry.getParentFile(), pid, 0, List.of("-Xmx128m"), false, NativeServicesMode.DISABLED, DaemonPriority.NORMAL);
            byte[] token = {1, 2, 3};
            var info = new DaemonInfo(address, context, token, DaemonState.valueOf(args[1]));
            ProcessMetaDataProvider metadata = new ProcessMetaDataProvider() {
                public String getProcessIdentifier() { return Long.toString(pid); }
                public String getProcessDisplayName() { return "Synthetic protocol fixture"; }
            };
            FileLockContentionHandler contention = new FileLockContentionHandler() {
                public void start(long id, Consumer<FileLockReleasedSignal> action) {}
                public void stop(long id) {}
                public int reservePort() { return -1; }
                public boolean maybePingOwner(int port, long id, String name, long elapsed, FileLockReleasedSignal signal) { return false; }
                public boolean isRunning() { return false; }
            };
            new PersistentDaemonRegistry(registry, new DefaultFileLockManager(metadata, contention), (file, mode) -> {}).store(info);
            long created = ProcessHandle.current().info().startInstant().orElseThrow().toEpochMilli();
            System.out.println("{\"pid\":" + pid + ",\"created\":" + created + "}"); System.out.flush();
            try (SocketChannel channel = server.accept()) {
                channel.configureBlocking(false);
                var type = Class.forName("org.gradle.internal.remote.internal.inet.SocketConnectCompletion");
                var ctor = type.getDeclaredConstructor(SocketChannel.class); ctor.setAccessible(true);
                var completion = (ConnectCompletion) ctor.newInstance(channel);
                RemoteConnection<Message> connection = completion.create(Serializers.stateful(DaemonMessageSerializer.create(BuildActionSerializer.create())));
                Message command = connection.receive();
                if (!(command instanceof StopWhenIdle) || !Arrays.equals(((Command) command).getToken(), token))
                    throw new IllegalStateException("Wrong shutdown command");
                connection.dispatch(new Success(null)); connection.flush();
                if (!(connection.receive() instanceof Finished)) throw new IllegalStateException("Missing finish");
                connection.stop();
            }
        }
    }
}
