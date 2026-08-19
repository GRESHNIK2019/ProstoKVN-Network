using System.Buffers.Binary;
using System.Diagnostics;
using System.Net;
using System.Net.Security;
using System.Net.Sockets;
using System.Security.Authentication;
using System.Text;

namespace ProstoKVN.Network.Core.Services;

internal static class Socks5Probe
{
    public static async Task<double?> MeasureHttpsAsync(int proxyPort, TimeSpan timeout, CancellationToken cancellationToken)
    {
        const string host = "www.gstatic.com";
        var started = Stopwatch.GetTimestamp();
        try
        {
            using var client = await ConnectAsync(proxyPort, host, 443, timeout, cancellationToken);
            await using var ssl = new SslStream(client.GetStream(), false);
            using var cts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            cts.CancelAfter(timeout);
            await ssl.AuthenticateAsClientAsync(new SslClientAuthenticationOptions
            {
                TargetHost = host,
                EnabledSslProtocols = SslProtocols.Tls12 | SslProtocols.Tls13,
            }, cts.Token);

            var request = Encoding.ASCII.GetBytes("GET /generate_204 HTTP/1.1\r\nHost: www.gstatic.com\r\nConnection: close\r\n\r\n");
            await ssl.WriteAsync(request, cts.Token);
            await ssl.FlushAsync(cts.Token);
            var buffer = new byte[512];
            var count = await ssl.ReadAsync(buffer, cts.Token);
            if (count <= 0) return null;
            var text = Encoding.ASCII.GetString(buffer, 0, count);
            if (!text.Contains(" 204 ", StringComparison.Ordinal) && !text.Contains(" 200 ", StringComparison.Ordinal)) return null;
            return Stopwatch.GetElapsedTime(started).TotalMilliseconds;
        }
        catch
        {
            return null;
        }
    }

    public static async Task<bool> TestConnectAsync(int proxyPort, string host, int port, TimeSpan timeout, CancellationToken cancellationToken)
    {
        try
        {
            using var client = await ConnectAsync(proxyPort, host, port, timeout, cancellationToken);
            return client.Connected;
        }
        catch { return false; }
    }

    public static async Task<bool> TestUdpDnsAsync(int proxyPort, TimeSpan timeout, CancellationToken cancellationToken)
    {
        using var control = new TcpClient();
        using var cts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        cts.CancelAfter(timeout);
        await control.ConnectAsync(IPAddress.Loopback, proxyPort, cts.Token);
        var stream = control.GetStream();
        await NegotiateAsync(stream, cts.Token);

        await stream.WriteAsync(new byte[] { 5, 3, 0, 1, 0, 0, 0, 0, 0, 0 }, cts.Token);
        var header = await ReadExactAsync(stream, 4, cts.Token);
        if (header[1] != 0) return false;
        var relayHost = await ReadAddressAsync(stream, header[3], cts.Token);
        var relayPortBytes = await ReadExactAsync(stream, 2, cts.Token);
        var relayPort = BinaryPrimitives.ReadUInt16BigEndian(relayPortBytes);
        if (relayHost is "0.0.0.0" or "::" or "") relayHost = "127.0.0.1";

        if (!IPAddress.TryParse(relayHost, out var relayAddress))
        {
            var addresses = await Dns.GetHostAddressesAsync(relayHost, cts.Token);
            relayAddress = addresses.FirstOrDefault(x => x.AddressFamily == AddressFamily.InterNetwork) ?? addresses.First();
        }

        using var udp = new UdpClient(relayAddress.AddressFamily);
        var dns = BuildDnsQuery();
        var packet = new byte[10 + dns.Length];
        packet[0] = packet[1] = packet[2] = 0;
        packet[3] = 1;
        IPAddress.Parse("1.1.1.1").GetAddressBytes().CopyTo(packet, 4);
        BinaryPrimitives.WriteUInt16BigEndian(packet.AsSpan(8, 2), 53);
        dns.CopyTo(packet, 10);

        await udp.SendAsync(packet, new IPEndPoint(relayAddress, relayPort), cts.Token);
        var response = await udp.ReceiveAsync(cts.Token);
        var data = response.Buffer;
        if (data.Length < 16 || data[0] != 0 || data[1] != 0) return false;
        var position = 3;
        var atyp = data[position++];
        position += atyp switch
        {
            1 => 4,
            4 => 16,
            3 when position < data.Length => 1 + data[position],
            _ => data.Length,
        };
        position += 2;
        return data.Length > position + 12;
    }

    private static async Task<TcpClient> ConnectAsync(int proxyPort, string host, int port, TimeSpan timeout, CancellationToken cancellationToken)
    {
        var client = new TcpClient();
        using var cts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        cts.CancelAfter(timeout);
        try
        {
            await client.ConnectAsync(IPAddress.Loopback, proxyPort, cts.Token);
            var stream = client.GetStream();
            await NegotiateAsync(stream, cts.Token);

            var hostBytes = Encoding.ASCII.GetBytes(host);
            if (hostBytes.Length > 255) throw new InvalidOperationException("Слишком длинное имя хоста");
            var request = new byte[7 + hostBytes.Length];
            request[0] = 5;
            request[1] = 1;
            request[2] = 0;
            request[3] = 3;
            request[4] = (byte)hostBytes.Length;
            hostBytes.CopyTo(request, 5);
            BinaryPrimitives.WriteUInt16BigEndian(request.AsSpan(5 + hostBytes.Length, 2), (ushort)port);
            await stream.WriteAsync(request, cts.Token);

            var header = await ReadExactAsync(stream, 4, cts.Token);
            if (header[1] != 0) throw new IOException($"SOCKS5 REP={header[1]}");
            _ = await ReadAddressAsync(stream, header[3], cts.Token);
            _ = await ReadExactAsync(stream, 2, cts.Token);
            return client;
        }
        catch
        {
            client.Dispose();
            throw;
        }
    }

    private static async Task NegotiateAsync(NetworkStream stream, CancellationToken cancellationToken)
    {
        await stream.WriteAsync(new byte[] { 5, 1, 0 }, cancellationToken);
        var response = await ReadExactAsync(stream, 2, cancellationToken);
        if (response[0] != 5 || response[1] != 0) throw new IOException("SOCKS5: сервер не принял NO AUTH");
    }

    private static async Task<string> ReadAddressAsync(NetworkStream stream, byte type, CancellationToken cancellationToken)
    {
        return type switch
        {
            1 => new IPAddress(await ReadExactAsync(stream, 4, cancellationToken)).ToString(),
            4 => new IPAddress(await ReadExactAsync(stream, 16, cancellationToken)).ToString(),
            3 => Encoding.ASCII.GetString(await ReadExactAsync(stream, (await ReadExactAsync(stream, 1, cancellationToken))[0], cancellationToken)),
            _ => throw new IOException($"SOCKS5: неизвестный ATYP={type}"),
        };
    }

    private static async Task<byte[]> ReadExactAsync(Stream stream, int length, CancellationToken cancellationToken)
    {
        var data = new byte[length];
        var offset = 0;
        while (offset < data.Length)
        {
            var count = await stream.ReadAsync(data.AsMemory(offset), cancellationToken);
            if (count == 0) throw new EndOfStreamException();
            offset += count;
        }
        return data;
    }

    private static byte[] BuildDnsQuery()
    {
        var id = (ushort)(Environment.TickCount & 0xFFFF);
        using var stream = new MemoryStream();
        Span<byte> header = stackalloc byte[12];
        BinaryPrimitives.WriteUInt16BigEndian(header[0..2], id);
        BinaryPrimitives.WriteUInt16BigEndian(header[2..4], 0x0100);
        BinaryPrimitives.WriteUInt16BigEndian(header[4..6], 1);
        stream.Write(header);
        stream.WriteByte(7);
        stream.Write(Encoding.ASCII.GetBytes("example"));
        stream.WriteByte(3);
        stream.Write(Encoding.ASCII.GetBytes("com"));
        stream.WriteByte(0);
        Span<byte> tail = stackalloc byte[4];
        BinaryPrimitives.WriteUInt16BigEndian(tail[0..2], 1);
        BinaryPrimitives.WriteUInt16BigEndian(tail[2..4], 1);
        stream.Write(tail);
        return stream.ToArray();
    }
}
