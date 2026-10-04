import java.io.*;
import java.net.*;
import java.nio.channels.*;
import java.util.*;
import org.gradle.api.Action;
import org.gradle.cache.FileLockReleasedSignal;
import org.gradle.cache.internal.DefaultFileLockManager;
import org.gradle.cache.internal.ProcessMetaDataProvider;
import org.gradle.cache.internal.locklistener.FileLockContentionHandler;
import org.gradle.internal.remote.internal.*;
import org.gradle.internal.remote.internal.inet.*;
import org.gradle.internal.serialize.*;
import org.gradle.launcher.daemon.configuration.DaemonParameters.Priority;
import org.gradle.launcher.daemon.context.DefaultDaemonContext;
import org.gradle.launcher.daemon.protocol.*;
import org.gradle.launcher.daemon.protocol.Message;
import org.gradle.launcher.daemon.registry.*;
import org.gradle.launcher.daemon.server.api.DaemonStateControl.State;
import org.gradle.tooling.internal.provider.action.BuildActionSerializer;

// Isolated old-protocol fixture; never starts a Gradle build or uses real tokens.
class SyntheticDaemon86 {
    public static void main(String[] args) throws Exception {
        long pid = ProcessHandle.current().pid();
        File registry = new File(args[0]);
        try (ServerSocketChannel server = ServerSocketChannel.open()) {
            server.bind(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
            int port = ((InetSocketAddress) server.getLocalAddress()).getPort();
            var address = new MultiChoiceAddress(UUID.randomUUID(), port, List.of(InetAddress.getLoopbackAddress()));
            var context = new DefaultDaemonContext(UUID.randomUUID().toString(), new File(System.getProperty("java.home")),
                registry.getParentFile(), pid, 0, List.of("-Xmx128m"), false, Priority.NORMAL);
            byte[] token = {1, 2, 3};
            var info = new DaemonInfo(address, context, token, State.valueOf(args[1]));
            ProcessMetaDataProvider metadata = new ProcessMetaDataProvider() {
                public String getProcessIdentifier() { return Long.toString(pid); }
                public String getProcessDisplayName() { return "Synthetic 8.6 fixture"; }
            };
            FileLockContentionHandler contention = new FileLockContentionHandler() {
                public void start(long id, Action<FileLockReleasedSignal> action) {}
                public void stop(long id) {}
                public int reservePort() { return -1; }
                public boolean maybePingOwner(int port, long id, String name, long elapsed, FileLockReleasedSignal signal) { return false; }
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
                if (args.length > 2 && args[2].equals("race")) {
                    System.out.println("racing_work_preserved"); System.out.flush();
                    new BufferedReader(new InputStreamReader(System.in)).readLine();
                }
            }
        }
    }
}
