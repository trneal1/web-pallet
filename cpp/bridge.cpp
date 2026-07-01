/*
 * bridge.cpp
 * ==========
 * Dependency-free Linux/WSL C++ version of python/bridge.py.
 *
 * It listens for browser WebSocket clients on port 8080 and TCP JSON-line
 * drawing clients on port 9000. TCP commands are broadcast to browsers, and
 * selected browser events are delivered to TCP clients that subscribe.
 *
 * Compile on Linux/WSL:
 *
 *     g++ -std=c++17 -O2 -Wall -Wextra -pedantic cpp/bridge.cpp -o bridge
 *
 * Run:
 *
 *     ./bridge
 *     ./bridge --host 0.0.0.0 --websocket-port 8080 --tcp-port 9000
 */

#include <arpa/inet.h>
#include <algorithm>
#include <array>
#include <cerrno>
#include <cctype>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <iostream>
#include <map>
#include <netdb.h>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <sys/select.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <unistd.h>
#include <vector>

namespace {

constexpr const char* DEFAULT_LISTEN_HOST = "0.0.0.0";
constexpr int DEFAULT_WEBSOCKET_PORT = 8080;
constexpr int DEFAULT_TCP_PORT = 9000;
constexpr std::size_t DEFAULT_TCP_LIMIT = 16 * 1024 * 1024;
constexpr std::size_t DEFAULT_REPLAY_LIMIT = 10000;
constexpr auto WEBSOCKET_SEND_TIMEOUT = std::chrono::seconds(5);
constexpr const char* WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";

struct Args {
    std::string host = DEFAULT_LISTEN_HOST;
    int websocket_port = DEFAULT_WEBSOCKET_PORT;
    int tcp_port = DEFAULT_TCP_PORT;
    std::size_t tcp_limit = DEFAULT_TCP_LIMIT;
    bool buffer_replay = true;
    std::size_t buffer_limit = DEFAULT_REPLAY_LIMIT;
};

struct BrowserStatus {
    std::map<std::string, std::string> values;
};

struct WebClient {
    int fd = -1;
    bool handshaken = false;
    std::string input;
    std::string output;
    std::optional<std::chrono::steady_clock::time_point> send_deadline;
    BrowserStatus status;
};

struct TcpClient {
    int fd = -1;
    std::string input;
    std::string output;
    bool subscribed = false;
    bool close_after_write = false;
    std::string peer;
};

[[noreturn]] void usage(int exit_code) {
    std::ostream& out = exit_code == 0 ? std::cout : std::cerr;
    out << "Usage: bridge [options]\n"
        << "\n"
        << "Bridge TCP drawing clients to browser WebSocket clients.\n"
        << "\n"
        << "Options:\n"
        << "  --host HOST             IP/interface to listen on (default: 0.0.0.0)\n"
        << "  --websocket-port PORT   browser WebSocket port (default: 8080)\n"
        << "  --tcp-port PORT         drawing TCP port (default: 9000)\n"
        << "  --tcp-limit BYTES       maximum bytes per TCP JSON line (default: 16777216)\n"
        << "  --buffer-replay         keep compact reconnect state for browsers (default)\n"
        << "  --no-buffer-replay      disable reconnect state replay\n"
        << "  --buffer-limit COUNT    maximum compact state commands retained, 0 disables the count limit (default: 10000)\n"
        << "  -h, --help              show this help\n";
    std::exit(exit_code);
}

std::string take_value(int& i, int argc, char* argv[], const std::string& name) {
    if (i + 1 >= argc) throw std::runtime_error(name + " requires a value");
    return argv[++i];
}

int parse_int(const std::string& value, const std::string& name) {
    size_t used = 0;
    int result = 0;
    try {
        result = std::stoi(value, &used);
    } catch (const std::exception&) {
        throw std::runtime_error(name + " must be an integer");
    }
    if (used != value.size()) throw std::runtime_error(name + " must be an integer");
    return result;
}

std::size_t parse_size(const std::string& value, const std::string& name) {
    size_t used = 0;
    unsigned long long result = 0;
    try {
        result = std::stoull(value, &used);
    } catch (const std::exception&) {
        throw std::runtime_error(name + " must be a non-negative integer");
    }
    if (used != value.size()) throw std::runtime_error(name + " must be a non-negative integer");
    return static_cast<std::size_t>(result);
}

Args parse_args(int argc, char* argv[]) {
    Args args;
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "-h" || arg == "--help") {
            usage(0);
        } else if (arg == "--host") {
            args.host = take_value(i, argc, argv, arg);
        } else if (arg == "--websocket-port") {
            args.websocket_port = parse_int(take_value(i, argc, argv, arg), arg);
        } else if (arg == "--tcp-port") {
            args.tcp_port = parse_int(take_value(i, argc, argv, arg), arg);
        } else if (arg == "--tcp-limit") {
            args.tcp_limit = parse_size(take_value(i, argc, argv, arg), arg);
        } else if (arg == "--buffer-replay") {
            args.buffer_replay = true;
        } else if (arg == "--no-buffer-replay") {
            args.buffer_replay = false;
        } else if (arg == "--buffer-limit") {
            args.buffer_limit = parse_size(take_value(i, argc, argv, arg), arg);
        } else {
            throw std::runtime_error("unknown option: " + arg);
        }
    }
    return args;
}

std::string json_escape(const std::string& value) {
    std::ostringstream out;
    for (unsigned char ch : value) {
        switch (ch) {
            case '"': out << "\\\""; break;
            case '\\': out << "\\\\"; break;
            case '\b': out << "\\b"; break;
            case '\f': out << "\\f"; break;
            case '\n': out << "\\n"; break;
            case '\r': out << "\\r"; break;
            case '\t': out << "\\t"; break;
            default:
                if (ch < 0x20) {
                    const char* hex = "0123456789abcdef";
                    out << "\\u00" << hex[(ch >> 4) & 0x0f] << hex[ch & 0x0f];
                } else {
                    out << static_cast<char>(ch);
                }
        }
    }
    return out.str();
}

std::string q(const std::string& value) {
    return "\"" + json_escape(value) + "\"";
}

std::string trim(std::string value) {
    while (!value.empty() && std::isspace(static_cast<unsigned char>(value.back()))) value.pop_back();
    std::size_t start = 0;
    while (start < value.size() && std::isspace(static_cast<unsigned char>(value[start]))) ++start;
    return value.substr(start);
}

std::string lower_ascii(std::string value) {
    for (char& ch : value) ch = static_cast<char>(std::tolower(static_cast<unsigned char>(ch)));
    return value;
}

bool looks_like_json_object(const std::string& json) {
    const std::string value = trim(json);
    return value.size() >= 2 && value.front() == '{' && value.back() == '}';
}

bool looks_like_json_array(const std::string& json) {
    const std::string value = trim(json);
    return value.size() >= 2 && value.front() == '[' && value.back() == ']';
}

std::string extract_json_string(const std::string& json, const std::string& key) {
    const std::string pattern = "\"" + key + "\"";
    std::size_t pos = json.find(pattern);
    if (pos == std::string::npos) return {};
    pos = json.find(':', pos + pattern.size());
    if (pos == std::string::npos) return {};
    pos = json.find('"', pos + 1);
    if (pos == std::string::npos) return {};
    ++pos;

    std::string value;
    while (pos < json.size()) {
        char ch = json[pos++];
        if (ch == '"') return value;
        if (ch != '\\') {
            value.push_back(ch);
            continue;
        }
        if (pos >= json.size()) return {};
        char esc = json[pos++];
        switch (esc) {
            case '"': value.push_back('"'); break;
            case '\\': value.push_back('\\'); break;
            case '/': value.push_back('/'); break;
            case 'b': value.push_back('\b'); break;
            case 'f': value.push_back('\f'); break;
            case 'n': value.push_back('\n'); break;
            case 'r': value.push_back('\r'); break;
            case 't': value.push_back('\t'); break;
            case 'u':
                if (pos + 4 > json.size()) return {};
                pos += 4;
                break;
            default: value.push_back(esc); break;
        }
    }
    return {};
}

std::string extract_json_value(const std::string& json, const std::string& key) {
    const std::string pattern = "\"" + key + "\"";
    std::size_t pos = json.find(pattern);
    if (pos == std::string::npos) return "null";
    pos = json.find(':', pos + pattern.size());
    if (pos == std::string::npos) return "null";
    ++pos;
    while (pos < json.size() && std::isspace(static_cast<unsigned char>(json[pos]))) ++pos;
    if (pos >= json.size()) return "null";

    if (json[pos] == '"') {
        std::size_t end = pos + 1;
        bool escaped = false;
        while (end < json.size()) {
            const char ch = json[end++];
            if (escaped) escaped = false;
            else if (ch == '\\') escaped = true;
            else if (ch == '"') return json.substr(pos, end - pos);
        }
        return "null";
    }

    std::size_t end = pos;
    int depth = 0;
    while (end < json.size()) {
        const char ch = json[end];
        if (ch == '[' || ch == '{') ++depth;
        if (ch == ']' || ch == '}') --depth;
        if (depth < 0 || (depth == 0 && ch == ',')) break;
        ++end;
    }
    return trim(json.substr(pos, end - pos));
}

bool json_value_truthy(const std::string& value) {
    return !value.empty() && value != "null" && value != "false" && value != "0";
}

uint32_t rol(uint32_t value, unsigned bits) {
    return (value << bits) | (value >> (32 - bits));
}

std::array<uint8_t, 20> sha1(const std::string& input) {
    uint32_t h0 = 0x67452301;
    uint32_t h1 = 0xefcdab89;
    uint32_t h2 = 0x98badcfe;
    uint32_t h3 = 0x10325476;
    uint32_t h4 = 0xc3d2e1f0;

    std::vector<uint8_t> data(input.begin(), input.end());
    const uint64_t bit_len = static_cast<uint64_t>(data.size()) * 8;
    data.push_back(0x80);
    while ((data.size() % 64) != 56) data.push_back(0);
    for (int i = 7; i >= 0; --i) data.push_back(static_cast<uint8_t>((bit_len >> (i * 8)) & 0xff));

    for (std::size_t chunk = 0; chunk < data.size(); chunk += 64) {
        uint32_t w[80] {};
        for (int i = 0; i < 16; ++i) {
            const std::size_t j = chunk + static_cast<std::size_t>(i) * 4;
            w[i] = (static_cast<uint32_t>(data[j]) << 24) |
                   (static_cast<uint32_t>(data[j + 1]) << 16) |
                   (static_cast<uint32_t>(data[j + 2]) << 8) |
                   static_cast<uint32_t>(data[j + 3]);
        }
        for (int i = 16; i < 80; ++i) w[i] = rol(w[i - 3] ^ w[i - 8] ^ w[i - 14] ^ w[i - 16], 1);

        uint32_t a = h0, b = h1, c = h2, d = h3, e = h4;
        for (int i = 0; i < 80; ++i) {
            uint32_t f = 0;
            uint32_t k = 0;
            if (i < 20) {
                f = (b & c) | ((~b) & d);
                k = 0x5a827999;
            } else if (i < 40) {
                f = b ^ c ^ d;
                k = 0x6ed9eba1;
            } else if (i < 60) {
                f = (b & c) | (b & d) | (c & d);
                k = 0x8f1bbcdc;
            } else {
                f = b ^ c ^ d;
                k = 0xca62c1d6;
            }
            const uint32_t temp = rol(a, 5) + f + e + k + w[i];
            e = d;
            d = c;
            c = rol(b, 30);
            b = a;
            a = temp;
        }

        h0 += a;
        h1 += b;
        h2 += c;
        h3 += d;
        h4 += e;
    }

    std::array<uint8_t, 20> digest {};
    const uint32_t words[5] = {h0, h1, h2, h3, h4};
    for (int i = 0; i < 5; ++i) {
        digest[static_cast<std::size_t>(i) * 4] = static_cast<uint8_t>((words[i] >> 24) & 0xff);
        digest[static_cast<std::size_t>(i) * 4 + 1] = static_cast<uint8_t>((words[i] >> 16) & 0xff);
        digest[static_cast<std::size_t>(i) * 4 + 2] = static_cast<uint8_t>((words[i] >> 8) & 0xff);
        digest[static_cast<std::size_t>(i) * 4 + 3] = static_cast<uint8_t>(words[i] & 0xff);
    }
    return digest;
}

std::string base64_encode(const uint8_t* data, std::size_t size) {
    static constexpr char table[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    std::string out;
    for (std::size_t i = 0; i < size; i += 3) {
        const uint32_t a = data[i];
        const uint32_t b = i + 1 < size ? data[i + 1] : 0;
        const uint32_t c = i + 2 < size ? data[i + 2] : 0;
        const uint32_t triple = (a << 16) | (b << 8) | c;
        out.push_back(table[(triple >> 18) & 0x3f]);
        out.push_back(table[(triple >> 12) & 0x3f]);
        out.push_back(i + 1 < size ? table[(triple >> 6) & 0x3f] : '=');
        out.push_back(i + 2 < size ? table[triple & 0x3f] : '=');
    }
    return out;
}

std::string websocket_accept_value(const std::string& key) {
    const auto digest = sha1(key + WEBSOCKET_GUID);
    return base64_encode(digest.data(), digest.size());
}

void set_nonblocking(int fd) {
    const int flags = fcntl(fd, F_GETFL, 0);
    if (flags == -1) throw std::runtime_error("fcntl(F_GETFL) failed: " + std::string(std::strerror(errno)));
    if (fcntl(fd, F_SETFL, flags | O_NONBLOCK) == -1) {
        throw std::runtime_error("fcntl(F_SETFL) failed: " + std::string(std::strerror(errno)));
    }
}

int listen_socket(const std::string& host, int port) {
    addrinfo hints {};
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    hints.ai_flags = AI_PASSIVE;

    addrinfo* results = nullptr;
    const std::string port_text = std::to_string(port);
    const int gai = getaddrinfo(host.c_str(), port_text.c_str(), &hints, &results);
    if (gai != 0) throw std::runtime_error("could not resolve " + host + ": " + gai_strerror(gai));

    int fd = -1;
    int last_errno = 0;
    for (addrinfo* rp = results; rp != nullptr; rp = rp->ai_next) {
        fd = socket(rp->ai_family, rp->ai_socktype, rp->ai_protocol);
        if (fd == -1) {
            last_errno = errno;
            continue;
        }
        int yes = 1;
        setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes));
        if (bind(fd, rp->ai_addr, rp->ai_addrlen) == 0 && listen(fd, SOMAXCONN) == 0) break;
        last_errno = errno;
        close(fd);
        fd = -1;
    }
    freeaddrinfo(results);
    if (fd == -1) throw std::runtime_error("listen failed on " + host + ":" + port_text + ": " + std::strerror(last_errno));
    set_nonblocking(fd);
    return fd;
}

std::string peer_name(int fd) {
    sockaddr_storage addr {};
    socklen_t len = sizeof(addr);
    if (getpeername(fd, reinterpret_cast<sockaddr*>(&addr), &len) == -1) return "unknown";
    char host[NI_MAXHOST] {};
    char service[NI_MAXSERV] {};
    const int rc = getnameinfo(reinterpret_cast<sockaddr*>(&addr), len, host, sizeof(host), service, sizeof(service),
                               NI_NUMERICHOST | NI_NUMERICSERV);
    if (rc != 0) return "unknown";
    return std::string(host) + ":" + service;
}

std::optional<std::string> http_header(const std::string& request, const std::string& name) {
    const std::string wanted = lower_ascii(name);
    std::size_t pos = 0;
    while (pos < request.size()) {
        const std::size_t end = request.find("\r\n", pos);
        if (end == std::string::npos || end == pos) break;
        const std::string line = request.substr(pos, end - pos);
        const std::size_t colon = line.find(':');
        if (colon != std::string::npos && lower_ascii(trim(line.substr(0, colon))) == wanted) {
            return trim(line.substr(colon + 1));
        }
        pos = end + 2;
    }
    return std::nullopt;
}

std::string websocket_text_frame(const std::string& payload) {
    std::string frame;
    frame.push_back(static_cast<char>(0x81));
    if (payload.size() <= 125) {
        frame.push_back(static_cast<char>(payload.size()));
    } else if (payload.size() <= 65535) {
        frame.push_back(126);
        frame.push_back(static_cast<char>((payload.size() >> 8) & 0xff));
        frame.push_back(static_cast<char>(payload.size() & 0xff));
    } else {
        frame.push_back(127);
        const uint64_t len = payload.size();
        for (int i = 7; i >= 0; --i) frame.push_back(static_cast<char>((len >> (i * 8)) & 0xff));
    }
    frame += payload;
    return frame;
}

std::optional<std::string> pop_websocket_message(std::string& buffer, bool& close_requested) {
    close_requested = false;
    if (buffer.size() < 2) return std::nullopt;

    const uint8_t b0 = static_cast<uint8_t>(buffer[0]);
    const uint8_t b1 = static_cast<uint8_t>(buffer[1]);
    const uint8_t opcode = b0 & 0x0f;
    const bool masked = (b1 & 0x80) != 0;
    uint64_t len = b1 & 0x7f;
    std::size_t pos = 2;

    if (len == 126) {
        if (buffer.size() < pos + 2) return std::nullopt;
        len = (static_cast<uint8_t>(buffer[pos]) << 8) | static_cast<uint8_t>(buffer[pos + 1]);
        pos += 2;
    } else if (len == 127) {
        if (buffer.size() < pos + 8) return std::nullopt;
        len = 0;
        for (int i = 0; i < 8; ++i) len = (len << 8) | static_cast<uint8_t>(buffer[pos + i]);
        pos += 8;
    }

    if (!masked || len > static_cast<uint64_t>(64 * 1024 * 1024)) {
        close_requested = true;
        return std::nullopt;
    }
    if (buffer.size() < pos + 4 + len) return std::nullopt;

    uint8_t mask[4] {
        static_cast<uint8_t>(buffer[pos]),
        static_cast<uint8_t>(buffer[pos + 1]),
        static_cast<uint8_t>(buffer[pos + 2]),
        static_cast<uint8_t>(buffer[pos + 3]),
    };
    pos += 4;

    std::string payload;
    payload.reserve(static_cast<std::size_t>(len));
    for (uint64_t i = 0; i < len; ++i) {
        payload.push_back(static_cast<char>(static_cast<uint8_t>(buffer[pos + i]) ^ mask[i % 4]));
    }
    buffer.erase(0, pos + static_cast<std::size_t>(len));

    if (opcode == 0x8) {
        close_requested = true;
        return std::nullopt;
    }
    if (opcode == 0x1) return payload;
    return std::string();
}

std::string browser_status_fields_json(const std::map<int, WebClient>& web_clients) {
    std::vector<const BrowserStatus*> browsers;
    std::size_t connected_clients = 0;
    for (const auto& item : web_clients) {
        if (!item.second.handshaken) continue;
        ++connected_clients;
        const auto width = item.second.status.values.find("viewport_width");
        const auto height = item.second.status.values.find("viewport_height");
        if (width != item.second.status.values.end() && height != item.second.status.values.end() &&
            json_value_truthy(width->second) && json_value_truthy(height->second)) {
            browsers.push_back(&item.second.status);
        }
    }

    std::ostringstream out;
    out << "\"web_clients\":" << connected_clients << ",\"browsers\":[";
    for (std::size_t i = 0; i < browsers.size(); ++i) {
        if (i) out << ",";
        out << "{";
        bool first = true;
        for (const auto& value : browsers[i]->values) {
            if (!first) out << ",";
            first = false;
            out << q(value.first) << ":" << value.second;
        }
        out << "}";
    }
    out << "]";

    if (!browsers.empty()) {
        for (const auto& value : browsers.front()->values) {
            out << "," << q(value.first) << ":" << value.second;
        }
    }
    return out.str();
}

void queue_tcp_json(TcpClient& client, const std::string& payload) {
    client.output += payload;
    client.output += "\n";
}

void queue_web_text(WebClient& client, const std::string& message) {
    if (client.output.empty()) {
        client.send_deadline = std::chrono::steady_clock::now() + WEBSOCKET_SEND_TIMEOUT;
    }
    client.output += websocket_text_frame(message);
}

void close_fd(int& fd) {
    if (fd != -1) {
        close(fd);
        fd = -1;
    }
}

class Bridge {
public:
    explicit Bridge(Args args)
        : args_(std::move(args)),
          ws_listen_fd_(listen_socket(args_.host, args_.websocket_port)),
          tcp_listen_fd_(listen_socket(args_.host, args_.tcp_port)) {}

    ~Bridge() {
        close_fd(ws_listen_fd_);
        close_fd(tcp_listen_fd_);
        for (auto& item : web_clients_) close_fd(item.second.fd);
        for (auto& item : tcp_clients_) close_fd(item.second.fd);
    }

    void run() {
        std::cout << "WebSocket server listening on ws://" << args_.host << ":" << args_.websocket_port << "\n";
        std::cout << "TCP server listening on " << args_.host << ":" << args_.tcp_port
                  << " with " << args_.tcp_limit << " byte read limit\n";
        std::cout << "Bridge reconnect state "
                  << (args_.buffer_replay ? "enabled" : "disabled");
        if (args_.buffer_replay) std::cout << " (" << args_.buffer_limit << " command limit)";
        std::cout << "\n";

        while (true) {
            remove_stalled_web_clients();

            fd_set read_fds;
            fd_set write_fds;
            FD_ZERO(&read_fds);
            FD_ZERO(&write_fds);

            int max_fd = std::max(ws_listen_fd_, tcp_listen_fd_);
            FD_SET(ws_listen_fd_, &read_fds);
            FD_SET(tcp_listen_fd_, &read_fds);

            for (const auto& item : web_clients_) {
                FD_SET(item.first, &read_fds);
                if (!item.second.output.empty()) FD_SET(item.first, &write_fds);
                max_fd = std::max(max_fd, item.first);
            }
            for (const auto& item : tcp_clients_) {
                FD_SET(item.first, &read_fds);
                if (!item.second.output.empty()) FD_SET(item.first, &write_fds);
                max_fd = std::max(max_fd, item.first);
            }

            timeval timeout;
            timeval* timeout_ptr = select_timeout(timeout);
            const int ready = select(max_fd + 1, &read_fds, &write_fds, nullptr, timeout_ptr);
            if (ready == -1) {
                if (errno == EINTR) continue;
                throw std::runtime_error("select failed: " + std::string(std::strerror(errno)));
            }

            remove_stalled_web_clients();

            if (FD_ISSET(ws_listen_fd_, &read_fds)) accept_web_clients();
            if (FD_ISSET(tcp_listen_fd_, &read_fds)) accept_tcp_clients();

            std::vector<int> web_fds;
            for (const auto& item : web_clients_) web_fds.push_back(item.first);
            for (int fd : web_fds) {
                if (web_clients_.count(fd) && FD_ISSET(fd, &read_fds)) read_web(fd);
                if (web_clients_.count(fd) && FD_ISSET(fd, &write_fds)) flush_web(fd);
            }

            std::vector<int> tcp_fds;
            for (const auto& item : tcp_clients_) tcp_fds.push_back(item.first);
            for (int fd : tcp_fds) {
                if (tcp_clients_.count(fd) && FD_ISSET(fd, &read_fds)) read_tcp(fd);
                if (tcp_clients_.count(fd) && FD_ISSET(fd, &write_fds)) flush_tcp(fd);
            }
        }
    }

private:
    Args args_;
    int ws_listen_fd_ = -1;
    int tcp_listen_fd_ = -1;
    std::map<int, WebClient> web_clients_;
    std::map<int, TcpClient> tcp_clients_;
    std::vector<std::string> replay_buffer_;

    std::size_t web_client_count() const {
        std::size_t count = 0;
        for (const auto& item : web_clients_) {
            if (item.second.handshaken) ++count;
        }
        return count;
    }

    timeval* select_timeout(timeval& timeout) const {
        std::optional<std::chrono::steady_clock::time_point> nearest;
        for (const auto& item : web_clients_) {
            if (item.second.send_deadline && (!nearest || *item.second.send_deadline < *nearest)) {
                nearest = item.second.send_deadline;
            }
        }
        if (!nearest) return nullptr;

        const auto remaining = std::max(
            std::chrono::steady_clock::duration::zero(),
            *nearest - std::chrono::steady_clock::now());
        const auto microseconds = std::chrono::duration_cast<std::chrono::microseconds>(remaining);
        timeout.tv_sec = static_cast<decltype(timeout.tv_sec)>(microseconds.count() / 1000000);
        timeout.tv_usec = static_cast<decltype(timeout.tv_usec)>(microseconds.count() % 1000000);
        return &timeout;
    }

    void remove_stalled_web_clients() {
        const auto now = std::chrono::steady_clock::now();
        std::vector<int> stalled;
        for (const auto& item : web_clients_) {
            if (item.second.send_deadline && now >= *item.second.send_deadline) {
                stalled.push_back(item.first);
            }
        }
        for (int fd : stalled) remove_web(fd);
    }

    void accept_web_clients() {
        while (true) {
            int fd = accept(ws_listen_fd_, nullptr, nullptr);
            if (fd == -1) {
                if (errno == EAGAIN || errno == EWOULDBLOCK) return;
                throw std::runtime_error("WebSocket accept failed: " + std::string(std::strerror(errno)));
            }
            set_nonblocking(fd);
            WebClient client;
            client.fd = fd;
            web_clients_[fd] = std::move(client);
        }
    }

    void accept_tcp_clients() {
        while (true) {
            int fd = accept(tcp_listen_fd_, nullptr, nullptr);
            if (fd == -1) {
                if (errno == EAGAIN || errno == EWOULDBLOCK) return;
                throw std::runtime_error("TCP accept failed: " + std::string(std::strerror(errno)));
            }
            set_nonblocking(fd);

            TcpClient client;
            client.fd = fd;
            client.peer = peer_name(fd);
            std::cout << "TCP client connected: " << client.peer << "\n";

            const bool connected = web_client_count() > 0;
            queue_tcp_json(client, "{\"status\":\"" + std::string(connected ? "connected" : "no_web_clients") +
                                   "\"," + browser_status_fields_json(web_clients_) + "}");
            tcp_clients_[fd] = std::move(client);
        }
    }

    void read_web(int fd) {
        char buffer[8192];
        while (true) {
            const ssize_t received = recv(fd, buffer, sizeof(buffer), 0);
            if (received == 0) {
                remove_web(fd);
                return;
            }
            if (received == -1) {
                if (errno == EAGAIN || errno == EWOULDBLOCK) break;
                if (errno == EINTR) continue;
                remove_web(fd);
                return;
            }
            web_clients_[fd].input.append(buffer, static_cast<std::size_t>(received));
        }

        WebClient& client = web_clients_[fd];
        if (!client.handshaken) {
            const std::size_t end = client.input.find("\r\n\r\n");
            if (end == std::string::npos) return;
            const std::string request = client.input.substr(0, end + 4);
            client.input.erase(0, end + 4);
            const auto key = http_header(request, "Sec-WebSocket-Key");
            if (!key) {
                remove_web(fd);
                return;
            }
            const std::string response =
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                "Sec-WebSocket-Accept: " + websocket_accept_value(*key) + "\r\n"
                "\r\n";
            client.output += response;
            client.handshaken = true;
            std::cout << "Web app connected\n";
            replay_to_web_client(client);
            publish_tcp_event("{\"type\":\"__pallet_browser_connected\"," + browser_status_fields_json(web_clients_) + "}");
        }

        while (web_clients_.count(fd)) {
            bool close_requested = false;
            auto message = pop_websocket_message(web_clients_[fd].input, close_requested);
            if (close_requested) {
                remove_web(fd);
                return;
            }
            if (!message) break;
            if (message->empty()) continue;
            handle_web_message(fd, *message);
        }
    }

    void handle_web_message(int fd, const std::string& message) {
        const std::string type = extract_json_string(message, "type");
        if (looks_like_json_object(message) && type == "__pallet_status") {
            static const std::vector<std::string> keys = {
                "viewport_width", "viewport_height", "content_width", "content_height",
                "scroll_x", "scroll_y", "buffer_width", "buffer_height", "device_pixel_ratio",
                "screen_width", "screen_height",
                "screen_avail_width", "screen_avail_height", "echarts_version",
            };
            BrowserStatus status;
            for (const std::string& key : keys) status.values[key] = extract_json_value(message, key);
            web_clients_[fd].status = std::move(status);
        } else if (type == "__pallet_terminal_input" ||
                   type == "__pallet_xterm_input" ||
                   type == "__pallet_xterm_resize" ||
                   type == "__pallet_ui_event" ||
                   type == "__pallet_chart_event" ||
                   type == "__pallet_script_loaded" ||
                   type == "__pallet_script_error") {
            publish_tcp_event(message);
        }
    }

    void read_tcp(int fd) {
        char buffer[8192];
        while (true) {
            const ssize_t received = recv(fd, buffer, sizeof(buffer), 0);
            if (received == 0) {
                remove_tcp(fd);
                return;
            }
            if (received == -1) {
                if (errno == EAGAIN || errno == EWOULDBLOCK) break;
                if (errno == EINTR) continue;
                remove_tcp(fd);
                return;
            }
            TcpClient& client = tcp_clients_[fd];
            client.input.append(buffer, static_cast<std::size_t>(received));
            if (client.input.size() > args_.tcp_limit) {
                queue_tcp_json(client, "{\"status\":\"error\",\"message\":\"TCP message is too large for the bridge read limit\"}");
                client.close_after_write = true;
                return;
            }
        }

        while (tcp_clients_.count(fd)) {
            TcpClient& client = tcp_clients_[fd];
            const std::size_t newline = client.input.find('\n');
            if (newline == std::string::npos) break;
            std::string line = trim(client.input.substr(0, newline));
            client.input.erase(0, newline + 1);
            handle_tcp_line(fd, line);
        }
    }

    void handle_tcp_line(int fd, const std::string& line) {
        TcpClient& client = tcp_clients_[fd];
        const bool is_object = looks_like_json_object(line);
        const bool is_array = looks_like_json_array(line);
        if (!is_object && !is_array) {
            queue_tcp_json(client, "{\"status\":\"error\",\"message\":\"invalid JSON command\"}");
            return;
        }

        const std::string type = is_object ? extract_json_string(line, "type") : std::string();
        if (type == "__pallet_subscribe_events") {
            client.subscribed = true;
            queue_tcp_json(client, "{\"status\":\"ok\",\"events\":\"subscribed\"}");
            return;
        }

        if (type == "__pallet_get_status") {
            queue_tcp_json(client, "{\"status\":\"ok\"," + browser_status_fields_json(web_clients_) + "}");
            return;
        }

        remember_for_replay(line, type, is_object);
        const std::size_t connected_clients = web_client_count();
        broadcast(line);
        queue_tcp_json(client, "{\"status\":\"ok\",\"web_clients\":" + std::to_string(connected_clients) +
                              ",\"buffered\":" + std::string(args_.buffer_replay ? "true" : "false") + "}");
    }

    void broadcast(const std::string& command) {
        for (auto& item : web_clients_) {
            if (item.second.handshaken) queue_web_text(item.second, command);
        }
    }

    void replay_to_web_client(WebClient& client) {
        if (!args_.buffer_replay || replay_buffer_.empty()) return;
        for (const std::string& command : replay_buffer_) {
            queue_web_text(client, command);
        }
    }

    void remember_for_replay(const std::string& command, const std::string& type, bool is_object) {
        if (!args_.buffer_replay) return;
        static const std::set<std::string> ignored_types = {
            "__pallet_get_status",
            "__pallet_subscribe_events",
            "__pallet_status",
            "__pallet_terminal_input",
            "__pallet_xterm_input",
            "__pallet_xterm_resize",
            "__pallet_ui_event",
            "__pallet_chart_event",
            "__pallet_script_loaded",
            "__pallet_script_error",
            "__pallet_client_disconnected",
        };
        if (!type.empty() && ignored_types.count(type)) return;

        if (!is_object) {
            replay_buffer_.push_back(command);
            trim_replay_buffer();
            return;
        }

        if (type == "clear") {
            forget_page(command_page_key(command));
            replay_buffer_.push_back(command);
            trim_replay_buffer();
            return;
        }
        if (type == "__pallet_delete_page" || type == "page_delete") {
            forget_page(command_page_key(command));
            trim_replay_buffer();
            return;
        }
        if (type == "__pallet_show_page" || type == "page_show") {
            replay_buffer_.erase(
                std::remove_if(replay_buffer_.begin(), replay_buffer_.end(), [](const std::string& item) {
                    const std::string item_type = extract_json_string(item, "type");
                    return item_type == "__pallet_show_page" || item_type == "page_show";
                }),
                replay_buffer_.end());
            replay_buffer_.push_back(command);
            trim_replay_buffer();
            return;
        }
        if (type == "__pallet_replace_group" || type == "group_replace") {
            replace_group_state(command);
            trim_replay_buffer();
            return;
        }
        if (type == "chart_remove" || type == "chart_delete") {
            forget_chart(command);
            trim_replay_buffer();
            return;
        }
        if (type == "chart_define" || type == "chart_create") {
            forget_chart(command);
            replay_buffer_.push_back(command);
            trim_replay_buffer();
            return;
        }
        if (type == "chart_option" && json_value_truthy(extract_json_value(command, "coalesce")) &&
            replace_previous_chart_option(command)) {
            return;
        }
        if (type == "chart_data" && !json_value_truthy(extract_json_value(command, "append")) &&
            replace_previous_chart_data(command)) {
            return;
        }
        if ((type == "chart_resize" || type == "chart_move") &&
            replace_previous_target_command(command, {"chart_resize", "chart_move"}, "chart", {"chart_define", "chart_create"})) {
            return;
        }
        if ((type == "chart_show" || type == "chart_hide") &&
            replace_previous_target_command(command, {"chart_show", "chart_hide"}, "chart", {"chart_define", "chart_create"})) {
            return;
        }
        if (is_ui_define_type(type)) {
            forget_ui_target(command, type);
            replay_buffer_.push_back(command);
            trim_replay_buffer();
            return;
        }
        if (type == "ui_control_update" &&
            replace_previous_target_command(command, {"ui_control_update"}, "control", {"ui_control"})) {
            return;
        }
        if (type == "ui_status_update" &&
            replace_previous_target_command(command, {"ui_status_update"}, "status", {"ui_status"})) {
            return;
        }
        if (type == "ui_table_update") {
            const std::string action = extract_json_string(command, "action").empty()
                ? "set"
                : extract_json_string(command, "action");
            if ((action == "set" || action == "clear") &&
                replace_previous_target_command(command, {"ui_table_update"}, "table", {"ui_table"})) {
                return;
            }
        }
        if (type == "terminal_define" || type == "terminal_xterm_define") {
            forget_terminal(command, type);
            replay_buffer_.push_back(command);
            trim_replay_buffer();
            return;
        }
        if ((type == "terminal_clear" || type == "terminal_xterm_clear") && coalesce_terminal_clear(command, type)) {
            return;
        }

        replay_buffer_.push_back(command);
        trim_replay_buffer();
    }

    void trim_replay_buffer() {
        if (args_.buffer_limit > 0 && replay_buffer_.size() > args_.buffer_limit) {
            replay_buffer_.erase(
                replay_buffer_.begin(),
                replay_buffer_.begin() + static_cast<std::ptrdiff_t>(replay_buffer_.size() - args_.buffer_limit));
        }
    }

    std::string command_page_key(const std::string& command) const {
        std::string page = extract_json_value(command, "palletPage");
        if (page == "null") page = extract_json_value(command, "page");
        return page;
    }

    std::string command_chart_id(const std::string& command) const {
        const std::string id = extract_json_string(command, "id");
        return id.empty() ? "chart" : id;
    }

    std::string command_id(const std::string& command, const std::string& fallback = "default") const {
        const std::string id = extract_json_string(command, "id");
        return id.empty() ? fallback : id;
    }

    std::string command_series_key(const std::string& command) const {
        const std::string series_id = extract_json_value(command, "seriesId");
        const std::string series_name = extract_json_value(command, "seriesName");
        const std::string series_index = extract_json_value(command, "seriesIndex");
        return series_id + "|" + series_name + "|" + (series_index == "null" ? "0" : series_index);
    }

    bool same_chart(const std::string& first, const std::string& second) const {
        return command_page_key(first) == command_page_key(second) &&
               command_chart_id(first) == command_chart_id(second);
    }

    bool is_chart_command_type(const std::string& type) const {
        return type == "chart_define" || type == "chart_create" ||
               type == "chart_option" || type == "chart_set_option" ||
               type == "chart_data" || type == "chart_append" ||
               type == "chart_resize" || type == "chart_move" ||
               type == "chart_show" || type == "chart_hide" ||
               type == "chart_remove" || type == "chart_delete";
    }

    void forget_page(const std::string& page_key) {
        replay_buffer_.erase(
            std::remove_if(replay_buffer_.begin(), replay_buffer_.end(), [&](const std::string& item) {
                return command_page_key(item) == page_key;
            }),
            replay_buffer_.end());
    }

    void forget_chart(const std::string& command) {
        replay_buffer_.erase(
            std::remove_if(replay_buffer_.begin(), replay_buffer_.end(), [&](const std::string& item) {
                return same_chart(item, command) && is_chart_command_type(extract_json_string(item, "type"));
            }),
            replay_buffer_.end());
    }

    bool is_ui_define_type(const std::string& type) const {
        return type == "ui_grid" || type == "ui_card" || type == "ui_control" ||
               type == "ui_status" || type == "ui_table";
    }

    std::string default_ui_id(const std::string& type) const {
        if (type == "ui_grid") return "default";
        if (type == "ui_card") return "card";
        if (type == "ui_control") return "control";
        if (type == "ui_status") return "status";
        if (type == "ui_table") return "table";
        return "default";
    }

    bool is_related_ui_type(const std::string& define_type, const std::string& item_type) const {
        if (define_type == "ui_grid") return item_type == "ui_grid";
        if (define_type == "ui_card") return item_type == "ui_card";
        if (define_type == "ui_control") return item_type == "ui_control" || item_type == "ui_control_update";
        if (define_type == "ui_status") return item_type == "ui_status" || item_type == "ui_status_update";
        if (define_type == "ui_table") return item_type == "ui_table" || item_type == "ui_table_update";
        return item_type == define_type;
    }

    void forget_ui_target(const std::string& command, const std::string& type) {
        const std::string page_key = command_page_key(command);
        const std::string id = command_id(command, default_ui_id(type));
        replay_buffer_.erase(
            std::remove_if(replay_buffer_.begin(), replay_buffer_.end(), [&](const std::string& item) {
                const std::string item_type = extract_json_string(item, "type");
                return command_page_key(item) == page_key &&
                       ((is_related_ui_type(type, item_type) && command_id(item, id) == id) ||
                        (type == "ui_card" && extract_json_string(item, "card") == id));
            }),
            replay_buffer_.end());
    }

    void forget_terminal(const std::string& command, const std::string& type) {
        const std::string page_key = command_page_key(command);
        const std::string id = command_id(command);
        replay_buffer_.erase(
            std::remove_if(replay_buffer_.begin(), replay_buffer_.end(), [&](const std::string& item) {
                const std::string item_type = extract_json_string(item, "type");
                const bool related = type == "terminal_xterm_define"
                    ? (item_type == "terminal_xterm_define" || item_type == "terminal_xterm_output" ||
                       item_type == "terminal_xterm_clear" || item_type == "terminal_xterm_font_size")
                    : (item_type == "terminal_define" || item_type == "terminal_write" || item_type == "terminal_clear");
                return command_page_key(item) == page_key && command_id(item) == id && related;
            }),
            replay_buffer_.end());
    }

    void replace_group_state(const std::string& command) {
        const std::string page_key = command_page_key(command);
        const std::string group = extract_json_string(command, "group");
        if (group.empty()) return;
        replay_buffer_.erase(
            std::remove_if(replay_buffer_.begin(), replay_buffer_.end(), [&](const std::string& item) {
                return command_page_key(item) == page_key && extract_json_string(item, "group") == group;
            }),
            replay_buffer_.end());
        replay_buffer_.push_back(command);
    }

    bool replace_previous_chart_option(const std::string& command) {
        for (auto it = replay_buffer_.rbegin(); it != replay_buffer_.rend(); ++it) {
            if (!same_chart(*it, command)) continue;
            const std::string previous_type = extract_json_string(*it, "type");
            if (previous_type == "chart_define" || previous_type == "chart_create") break;
            if (previous_type == "chart_option" && json_value_truthy(extract_json_value(*it, "coalesce"))) {
                *it = command;
                return true;
            }
        }
        return false;
    }

    bool replace_previous_chart_data(const std::string& command) {
        const std::string series_key = command_series_key(command);
        for (auto it = replay_buffer_.rbegin(); it != replay_buffer_.rend(); ++it) {
            if (!same_chart(*it, command)) continue;
            const std::string previous_type = extract_json_string(*it, "type");
            if (previous_type == "chart_define" || previous_type == "chart_create") break;
            if (previous_type == "chart_data" && command_series_key(*it) == series_key) {
                *it = command;
                return true;
            }
        }
        return false;
    }

    bool replace_previous_target_command(
        const std::string& command,
        const std::set<std::string>& replace_types,
        const std::string& default_id,
        const std::set<std::string>& stop_types = {}) {
        const std::string page_key = command_page_key(command);
        const std::string id = command_id(command, default_id);
        for (auto it = replay_buffer_.rbegin(); it != replay_buffer_.rend(); ++it) {
            if (command_page_key(*it) != page_key || command_id(*it, default_id) != id) continue;
            const std::string previous_type = extract_json_string(*it, "type");
            if (stop_types.count(previous_type)) break;
            if (replace_types.count(previous_type)) {
                *it = command;
                return true;
            }
        }
        return false;
    }

    bool coalesce_terminal_clear(const std::string& command, const std::string& type) {
        const std::string page_key = command_page_key(command);
        const std::string id = command_id(command);
        const bool is_xterm = type == "terminal_xterm_clear";
        const std::string define_type = is_xterm ? "terminal_xterm_define" : "terminal_define";
        const std::set<std::string> removable_types = is_xterm
            ? std::set<std::string>{"terminal_xterm_output", "terminal_xterm_clear"}
            : std::set<std::string>{"terminal_write", "terminal_clear"};
        std::vector<std::string> kept;
        kept.reserve(replay_buffer_.size());
        std::size_t insert_at = replay_buffer_.size();
        bool removed = false;

        for (const std::string& item : replay_buffer_) {
            const bool same_target = command_page_key(item) == page_key && command_id(item) == id;
            const std::string item_type = extract_json_string(item, "type");
            if (same_target && item_type == define_type) insert_at = kept.size() + 1;
            if (same_target && removable_types.count(item_type)) {
                removed = true;
                continue;
            }
            kept.push_back(item);
        }
        if (!removed) return false;
        insert_at = std::min(insert_at, kept.size());
        kept.insert(kept.begin() + static_cast<std::ptrdiff_t>(insert_at), command);
        replay_buffer_.swap(kept);
        return true;
    }

    void publish_tcp_event(const std::string& event_json) {
        for (auto& item : tcp_clients_) {
            if (item.second.subscribed) {
                queue_tcp_json(item.second, "{\"status\":\"event\",\"event\":" + event_json + "}");
            }
        }
    }

    void flush_web(int fd) {
        WebClient& client = web_clients_[fd];
        const std::size_t pending = client.output.size();
        flush_output(fd, client.output);
        if (client.fd == -1) {
            remove_web(fd);
        } else if (client.output.empty()) {
            client.send_deadline.reset();
        } else if (client.output.size() < pending) {
            client.send_deadline = std::chrono::steady_clock::now() + WEBSOCKET_SEND_TIMEOUT;
        }
    }

    void flush_tcp(int fd) {
        TcpClient& client = tcp_clients_[fd];
        flush_output(fd, client.output);
        if (client.fd == -1 || (client.output.empty() && client.close_after_write)) remove_tcp(fd);
    }

    template <typename ClientOutput>
    void flush_output(int fd, ClientOutput& output) {
        while (!output.empty()) {
            const ssize_t sent = send(fd, output.data(), output.size(), MSG_NOSIGNAL);
            if (sent == -1) {
                if (errno == EAGAIN || errno == EWOULDBLOCK) return;
                if (errno == EINTR) continue;
                output.clear();
                return;
            }
            output.erase(0, static_cast<std::size_t>(sent));
        }
    }

    void remove_web(int fd) {
        auto it = web_clients_.find(fd);
        if (it == web_clients_.end()) return;
        close_fd(it->second.fd);
        web_clients_.erase(it);
        std::cout << "Web app disconnected\n";
    }

    void remove_tcp(int fd) {
        auto it = tcp_clients_.find(fd);
        if (it == tcp_clients_.end()) return;
        const std::string peer = it->second.peer;
        close_fd(it->second.fd);
        tcp_clients_.erase(it);
        if (web_client_count() > 0) {
            broadcast("{\"type\":\"__pallet_client_disconnected\",\"client\":" + q(peer) + "}");
        }
        std::cout << "TCP client disconnected: " << peer << "\n";
    }
};

}  // namespace

int main(int argc, char* argv[]) {
    try {
        Bridge bridge(parse_args(argc, argv));
        bridge.run();
    } catch (const std::exception& exc) {
        std::cerr << "Failed: " << exc.what() << "\n";
        return 1;
    }
    return 0;
}
