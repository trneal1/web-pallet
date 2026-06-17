/*
 * pallet_xterm.cpp
 * =================
 * PTY-backed interactive terminal for Web Pallet.
 *
 * Start the bridge and connect pallet.html first:
 *
 *     python3 python/bridge.py
 *
 * Compile on Linux:
 *
 *     g++ -std=c++17 -O2 -Wall -Wextra -pedantic cpp/pallet_xterm.cpp -o pallet_xterm
 *
 * Run:
 *
 *     ./pallet_xterm --id shell --clear --title "Shell"
 *
 * This starts a real shell under a Linux pseudoterminal. Full-screen programs
 * such as vi, nano, top, less, and htop can use cursor movement and raw keys.
 */

#include <arpa/inet.h>
#include <cerrno>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <iostream>
#include <netdb.h>
#include <optional>
#include <pty.h>
#include <sstream>
#include <stdexcept>
#include <string>
#include <sys/ioctl.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <termios.h>
#include <unistd.h>
#include <utility>

namespace {

constexpr const char* DEFAULT_BRIDGE_HOST = "127.0.0.1";
constexpr int DEFAULT_BRIDGE_PORT = 9000;

struct Args {
    std::string id = "shell";
    std::string bridge_host = DEFAULT_BRIDGE_HOST;
    int bridge_port = DEFAULT_BRIDGE_PORT;
    std::optional<int> port;
    std::optional<std::string> page;
    bool clear = false;
    bool define = true;
    int x = 24;
    int y = 24;
    int width = 820;
    int height = 420;
    int font_size = 14;
    std::string title = "Pallet Shell";
    std::string background = "#020617";
    std::string text_color = "#E5E7EB";
    double timeout = 5.0;
};

struct XtermEvent {
    enum class Type { Input, Resize, BrowserConnected, Ignore };
    Type type = Type::Ignore;
    std::string id;
    std::string data;
    std::optional<std::string> page;
    int cols = 0;
    int rows = 0;
};

[[noreturn]] void usage(int exit_code) {
    std::ostream& out = exit_code == 0 ? std::cout : std::cerr;
    out << "Usage: pallet_xterm [options]\n"
        << "\n"
        << "Create a PTY-backed Web Pallet terminal. Commands and full-screen\n"
        << "programs run on the computer where this program is running.\n"
        << "\n"
        << "Options:\n"
        << "  --id ID                 terminal region id (default: shell)\n"
        << "  --bridge-host HOST      bridge TCP host or IP address (default: 127.0.0.1)\n"
        << "  --bridge-port PORT      bridge TCP port (default: 9000)\n"
        << "  --port PORT             alias for --bridge-port\n"
        << "  --page PAGE             pallet page to draw on\n"
        << "  --clear                 clear the xterm region on start\n"
        << "  --define                define the xterm region on start (default)\n"
        << "  --no-define             do not define the xterm region on start\n"
        << "  --x N                   region x position (default: 24)\n"
        << "  --y N                   region y position (default: 24)\n"
        << "  --width N               region width (default: 820)\n"
        << "  --height N              region height (default: 420)\n"
        << "  --font-size N           terminal font size (default: 14)\n"
        << "  --title TEXT            region title metadata (default: Pallet Shell)\n"
        << "  --background COLOR      region background color (default: #020617)\n"
        << "  --text-color COLOR      region text color (default: #E5E7EB)\n"
        << "  --timeout SECONDS       bridge connection timeout in seconds (default: 5.0)\n"
        << "  -h, --help              show this help\n";
    std::exit(exit_code);
}

std::string take_value(int& i, int argc, char* argv[], const std::string& name) {
    if (i + 1 >= argc) {
        throw std::runtime_error(name + " requires a value");
    }
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
    if (used != value.size()) {
        throw std::runtime_error(name + " must be an integer");
    }
    return result;
}

double parse_double(const std::string& value, const std::string& name) {
    size_t used = 0;
    double result = 0.0;
    try {
        result = std::stod(value, &used);
    } catch (const std::exception&) {
        throw std::runtime_error(name + " must be a number");
    }
    if (used != value.size() || result < 0.0) {
        throw std::runtime_error(name + " must be a non-negative number");
    }
    return result;
}

Args parse_args(int argc, char* argv[]) {
    Args args;
    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "-h" || arg == "--help") {
            usage(0);
        } else if (arg == "--id") {
            args.id = take_value(i, argc, argv, arg);
        } else if (arg == "--bridge-host") {
            args.bridge_host = take_value(i, argc, argv, arg);
        } else if (arg == "--bridge-port") {
            args.bridge_port = parse_int(take_value(i, argc, argv, arg), arg);
        } else if (arg == "--port") {
            args.port = parse_int(take_value(i, argc, argv, arg), arg);
        } else if (arg == "--page") {
            args.page = take_value(i, argc, argv, arg);
        } else if (arg == "--clear") {
            args.clear = true;
        } else if (arg == "--define") {
            args.define = true;
        } else if (arg == "--no-define") {
            args.define = false;
        } else if (arg == "--x") {
            args.x = parse_int(take_value(i, argc, argv, arg), arg);
        } else if (arg == "--y") {
            args.y = parse_int(take_value(i, argc, argv, arg), arg);
        } else if (arg == "--width") {
            args.width = parse_int(take_value(i, argc, argv, arg), arg);
        } else if (arg == "--height") {
            args.height = parse_int(take_value(i, argc, argv, arg), arg);
        } else if (arg == "--font-size") {
            args.font_size = parse_int(take_value(i, argc, argv, arg), arg);
        } else if (arg == "--title") {
            args.title = take_value(i, argc, argv, arg);
        } else if (arg == "--background") {
            args.background = take_value(i, argc, argv, arg);
        } else if (arg == "--text-color") {
            args.text_color = take_value(i, argc, argv, arg);
        } else if (arg == "--timeout") {
            args.timeout = parse_double(take_value(i, argc, argv, arg), arg);
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

std::optional<std::string> extract_json_string(const std::string& json, const std::string& key) {
    const std::string pattern = "\"" + key + "\"";
    size_t pos = json.find(pattern);
    if (pos == std::string::npos) return std::nullopt;
    pos = json.find(':', pos + pattern.size());
    if (pos == std::string::npos) return std::nullopt;
    pos = json.find('"', pos + 1);
    if (pos == std::string::npos) return std::nullopt;
    ++pos;

    std::string value;
    while (pos < json.size()) {
        char ch = json[pos++];
        if (ch == '"') return value;
        if (ch != '\\') {
            value.push_back(ch);
            continue;
        }
        if (pos >= json.size()) return std::nullopt;
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
            case 'u': {
                if (pos + 4 > json.size()) return std::nullopt;
                const std::string hex = json.substr(pos, 4);
                pos += 4;
                char* end = nullptr;
                long code = std::strtol(hex.c_str(), &end, 16);
                if (end && *end == '\0' && code >= 0 && code <= 0x7f) {
                    value.push_back(static_cast<char>(code));
                }
                break;
            }
            default: value.push_back(esc); break;
        }
    }
    return std::nullopt;
}

std::optional<int> extract_json_int(const std::string& json, const std::string& key) {
    const std::string pattern = "\"" + key + "\"";
    size_t pos = json.find(pattern);
    if (pos == std::string::npos) return std::nullopt;
    pos = json.find(':', pos + pattern.size());
    if (pos == std::string::npos) return std::nullopt;
    ++pos;
    while (pos < json.size() && std::isspace(static_cast<unsigned char>(json[pos]))) ++pos;
    size_t end = pos;
    while (end < json.size() && (std::isdigit(static_cast<unsigned char>(json[end])) || json[end] == '-')) ++end;
    if (end == pos) return std::nullopt;
    return parse_int(json.substr(pos, end - pos), key);
}

XtermEvent parse_xterm_event(const std::string& line) {
    XtermEvent event;
    if (line.find("\"status\":\"event\"") == std::string::npos &&
        line.find("\"status\": \"event\"") == std::string::npos) {
        return event;
    }

    if (line.find("\"type\":\"__pallet_browser_connected\"") != std::string::npos ||
        line.find("\"type\": \"__pallet_browser_connected\"") != std::string::npos) {
        event.type = XtermEvent::Type::BrowserConnected;
        return event;
    }

    const auto id = extract_json_string(line, "id");
    if (!id) return event;
    event.id = *id;
    event.page = extract_json_string(line, "page");

    if (line.find("\"type\":\"__pallet_xterm_input\"") != std::string::npos ||
        line.find("\"type\": \"__pallet_xterm_input\"") != std::string::npos) {
        const auto data = extract_json_string(line, "data");
        if (!data) return event;
        event.type = XtermEvent::Type::Input;
        event.data = *data;
        return event;
    }

    if (line.find("\"type\":\"__pallet_xterm_resize\"") != std::string::npos ||
        line.find("\"type\": \"__pallet_xterm_resize\"") != std::string::npos) {
        const auto cols = extract_json_int(line, "cols");
        const auto rows = extract_json_int(line, "rows");
        if (!cols || !rows) return event;
        event.type = XtermEvent::Type::Resize;
        event.cols = *cols;
        event.rows = *rows;
        return event;
    }

    return event;
}

void write_all(int fd, const std::string& data) {
    const char* ptr = data.data();
    size_t remaining = data.size();
    while (remaining > 0) {
        ssize_t written = ::write(fd, ptr, remaining);
        if (written == -1) {
            if (errno == EINTR) continue;
            throw std::runtime_error("write failed: " + std::string(std::strerror(errno)));
        }
        ptr += written;
        remaining -= static_cast<size_t>(written);
    }
}

void resize_pty(int pty_fd, int cols, int rows) {
    if (cols <= 0 || rows <= 0) return;
    winsize ws {};
    ws.ws_col = static_cast<unsigned short>(cols);
    ws.ws_row = static_cast<unsigned short>(rows);
    (void)::ioctl(pty_fd, TIOCSWINSZ, &ws);
}

class PalletConnection {
public:
    PalletConnection(std::string host, int port, double timeout_seconds)
        : host_(std::move(host)), port_(port), timeout_seconds_(timeout_seconds) {}

    ~PalletConnection() {
        close();
    }

    PalletConnection(const PalletConnection&) = delete;
    PalletConnection& operator=(const PalletConnection&) = delete;

    int fd() const {
        return fd_;
    }

    void connect() {
        addrinfo hints {};
        hints.ai_family = AF_UNSPEC;
        hints.ai_socktype = SOCK_STREAM;

        addrinfo* results = nullptr;
        const std::string port_text = std::to_string(port_);
        const int gai = getaddrinfo(host_.c_str(), port_text.c_str(), &hints, &results);
        if (gai != 0) {
            throw std::runtime_error("could not resolve bridge host " + host_ + ": " + gai_strerror(gai));
        }

        int last_errno = 0;
        for (addrinfo* rp = results; rp != nullptr; rp = rp->ai_next) {
            fd_ = socket(rp->ai_family, rp->ai_socktype, rp->ai_protocol);
            if (fd_ == -1) {
                last_errno = errno;
                continue;
            }
            if (connect_with_timeout(rp->ai_addr, rp->ai_addrlen)) break;
            last_errno = errno;
            close();
        }
        freeaddrinfo(results);

        if (fd_ == -1) {
            throw std::runtime_error("could not connect to bridge TCP server at " + host_ + ":" +
                                     std::to_string(port_) + ": " + std::strerror(last_errno));
        }

        const std::string hello = read_line();
        if (hello.find("\"status\":\"no_web_clients\"") != std::string::npos ||
            hello.find("\"status\": \"no_web_clients\"") != std::string::npos) {
            close();
            throw std::runtime_error("bridge is running, but no browser pallet is connected");
        }
    }

    std::string xterm_region_definition(const Args& args) const {
        std::ostringstream cmd;
        cmd << "{\"type\":\"terminal_xterm_define\""
            << ",\"id\":" << q(args.id)
            << (args.page ? ",\"page\":" + q(*args.page) : "")
            << ",\"x\":" << args.x
            << ",\"y\":" << args.y
            << ",\"width\":" << args.width
            << ",\"height\":" << args.height
            << ",\"title\":" << q(args.title)
            << ",\"background\":" << q(args.background)
            << ",\"color\":" << q(args.text_color)
            << ",\"border\":\"#334155\""
            << ",\"fontSize\":" << args.font_size
            << ",\"scrollback\":2000"
            << "}";
        return cmd.str();
    }

    void define_xterm_region(const Args& args, int pty_fd) {
        command(xterm_region_definition(args), pty_fd, args);
    }

    void subscribe_events(int pty_fd, const Args& args) {
        command("{\"type\":\"__pallet_subscribe_events\"}", pty_fd, args);
    }

    void clear_xterm_region(const Args& args, int pty_fd) {
        std::string cmd = "{\"type\":\"terminal_xterm_clear\",\"id\":" + q(args.id);
        if (args.page) {
            cmd += ",\"page\":" + q(*args.page);
        }
        cmd += "}";
        command(cmd, pty_fd, args);
    }

    void write_xterm_output(const Args& args, const std::string& data, int pty_fd) {
        std::string cmd = "{\"type\":\"terminal_xterm_output\",\"id\":" + q(args.id) + ",\"data\":" + q(data);
        if (args.page) {
            cmd += ",\"page\":" + q(*args.page);
        }
        cmd += "}";
        command(cmd, pty_fd, args);
    }

    bool read_and_handle_event(const Args& args, int pty_fd) {
        const std::string line = read_line();
        XtermEvent event = parse_xterm_event(line);
        return handle_event(event, args, pty_fd);
    }

private:
    std::string host_;
    int port_;
    double timeout_seconds_;
    int fd_ = -1;
    std::string read_buffer_;

    bool connect_with_timeout(const sockaddr* addr, socklen_t len) {
        const int flags = fcntl_get();
        fcntl_set(flags | O_NONBLOCK);

        const int rc = ::connect(fd_, addr, len);
        if (rc == 0) {
            fcntl_set(flags);
            return true;
        }
        if (errno != EINPROGRESS) {
            fcntl_set(flags);
            return false;
        }

        fd_set write_fds;
        FD_ZERO(&write_fds);
        FD_SET(fd_, &write_fds);

        timeval tv {};
        tv.tv_sec = static_cast<time_t>(std::floor(timeout_seconds_));
        tv.tv_usec = static_cast<suseconds_t>((timeout_seconds_ - std::floor(timeout_seconds_)) * 1000000.0);

        const int selected = select(fd_ + 1, nullptr, &write_fds, nullptr, timeout_seconds_ == 0.0 ? nullptr : &tv);
        if (selected <= 0) {
            errno = selected == 0 ? ETIMEDOUT : errno;
            fcntl_set(flags);
            return false;
        }

        int error = 0;
        socklen_t error_len = sizeof(error);
        if (getsockopt(fd_, SOL_SOCKET, SO_ERROR, &error, &error_len) == -1) {
            fcntl_set(flags);
            return false;
        }
        if (error != 0) {
            errno = error;
            fcntl_set(flags);
            return false;
        }

        fcntl_set(flags);
        return true;
    }

    int fcntl_get() {
        const int flags = ::fcntl(fd_, F_GETFL, 0);
        if (flags == -1) {
            throw std::runtime_error("fcntl(F_GETFL) failed: " + std::string(std::strerror(errno)));
        }
        return flags;
    }

    void fcntl_set(int flags) {
        if (::fcntl(fd_, F_SETFL, flags) == -1) {
            throw std::runtime_error("fcntl(F_SETFL) failed: " + std::string(std::strerror(errno)));
        }
    }

    void close() {
        if (fd_ != -1) {
            ::close(fd_);
            fd_ = -1;
        }
    }

    void send_all(const std::string& payload) {
        const char* data = payload.data();
        size_t remaining = payload.size();
        while (remaining > 0) {
            const ssize_t sent = ::send(fd_, data, remaining, MSG_NOSIGNAL);
            if (sent == -1) {
                if (errno == EINTR) continue;
                throw std::runtime_error("bridge write failed: " + std::string(std::strerror(errno)));
            }
            data += sent;
            remaining -= static_cast<size_t>(sent);
        }
    }

    std::string read_line() {
        while (true) {
            const size_t newline = read_buffer_.find('\n');
            if (newline != std::string::npos) {
                std::string line = read_buffer_.substr(0, newline);
                read_buffer_.erase(0, newline + 1);
                return line;
            }

            char buffer[4096];
            const ssize_t received = ::recv(fd_, buffer, sizeof(buffer), 0);
            if (received == 0) {
                throw std::runtime_error("bridge closed the TCP connection");
            }
            if (received == -1) {
                if (errno == EINTR) continue;
                throw std::runtime_error("bridge read failed: " + std::string(std::strerror(errno)));
            }
            read_buffer_.append(buffer, static_cast<size_t>(received));
        }
    }

    bool handle_event(const XtermEvent& event, const Args& args, int pty_fd) {
        if (event.type == XtermEvent::Type::Ignore) return false;

        if (event.type == XtermEvent::Type::BrowserConnected) {
            if (args.define) {
                define_xterm_region(args, pty_fd);
            }
            return true;
        }

        if (event.id != args.id || !matches_page(event, args)) return false;

        if (event.type == XtermEvent::Type::Input) {
            write_all(pty_fd, event.data);
            return true;
        }

        if (event.type == XtermEvent::Type::Resize) {
            resize_pty(pty_fd, event.cols, event.rows);
            return true;
        }

        return false;
    }

    bool matches_page(const XtermEvent& event, const Args& args) const {
        if (args.page) {
            return event.page && *event.page == *args.page;
        }
        return !event.page;
    }

    void command(const std::string& json, int pty_fd, const Args& args) {
        send_all(json + "\n");
        while (true) {
            const std::string response = read_line();
            XtermEvent event = parse_xterm_event(response);
            if (event.type != XtermEvent::Type::Ignore) {
                if (event.type == XtermEvent::Type::BrowserConnected) {
                    if (args.define) {
                        send_all(xterm_region_definition(args) + "\n");
                    }
                    continue;
                }
                if (event.id != args.id || !matches_page(event, args)) {
                    continue;
                }
                if (event.type == XtermEvent::Type::Input) {
                    write_all(pty_fd, event.data);
                } else if (event.type == XtermEvent::Type::Resize) {
                    resize_pty(pty_fd, event.cols, event.rows);
                }
                continue;
            }
            return;
        }
    }
};

pid_t spawn_shell(int& pty_fd, int cols, int rows) {
    winsize ws {};
    ws.ws_col = static_cast<unsigned short>(std::max(2, cols));
    ws.ws_row = static_cast<unsigned short>(std::max(2, rows));

    pid_t pid = ::forkpty(&pty_fd, nullptr, nullptr, &ws);
    if (pid == -1) {
        throw std::runtime_error("forkpty failed: " + std::string(std::strerror(errno)));
    }

    if (pid == 0) {
        ::setenv("TERM", "xterm-256color", 1);
        const char* shell = std::getenv("SHELL");
        if (!shell || !*shell) shell = "/bin/bash";
        ::execlp(shell, shell, static_cast<char*>(nullptr));
        ::execlp("/bin/sh", "sh", static_cast<char*>(nullptr));
        _exit(127);
    }

    return pid;
}

void event_loop(PalletConnection& pallet, const Args& args, int pty_fd, pid_t child_pid) {
    while (true) {
        int status = 0;
        pid_t waited = ::waitpid(child_pid, &status, WNOHANG);
        if (waited == child_pid) break;

        fd_set read_fds;
        FD_ZERO(&read_fds);
        FD_SET(pty_fd, &read_fds);
        FD_SET(pallet.fd(), &read_fds);
        int max_fd = std::max(pty_fd, pallet.fd());

        const int ready = ::select(max_fd + 1, &read_fds, nullptr, nullptr, nullptr);
        if (ready == -1) {
            if (errno == EINTR) continue;
            throw std::runtime_error("select failed: " + std::string(std::strerror(errno)));
        }

        if (FD_ISSET(pallet.fd(), &read_fds)) {
            pallet.read_and_handle_event(args, pty_fd);
        }

        if (FD_ISSET(pty_fd, &read_fds)) {
            char buffer[8192];
            const ssize_t received = ::read(pty_fd, buffer, sizeof(buffer));
            if (received == 0) break;
            if (received == -1) {
                if (errno == EINTR) continue;
                if (errno == EIO) break;
                throw std::runtime_error("PTY read failed: " + std::string(std::strerror(errno)));
            }
            pallet.write_xterm_output(args, std::string(buffer, static_cast<size_t>(received)), pty_fd);
        }
    }
}

}  // namespace

int main(int argc, char* argv[]) {
    int pty_fd = -1;
    pid_t child_pid = -1;

    try {
        Args args = parse_args(argc, argv);
        const int bridge_port = args.port.value_or(args.bridge_port);

        const int approx_cols = std::max(2, (args.width - 10) / std::max(6, static_cast<int>(std::round(args.font_size * 0.62))));
        const int approx_rows = std::max(2, (args.height - 10) / std::max(10, static_cast<int>(std::round(args.font_size * 1.15))));
        child_pid = spawn_shell(pty_fd, approx_cols, approx_rows);

        PalletConnection pallet(args.bridge_host, bridge_port, args.timeout);
        pallet.connect();
        pallet.subscribe_events(pty_fd, args);

        if (args.define) {
            pallet.define_xterm_region(args, pty_fd);
        }
        if (args.clear) {
            pallet.clear_xterm_region(args, pty_fd);
        }

        event_loop(pallet, args, pty_fd, child_pid);
    } catch (const std::exception& exc) {
        std::cerr << "Failed: " << exc.what() << "\n";
        if (child_pid > 0) {
            ::kill(child_pid, SIGHUP);
        }
        if (pty_fd != -1) {
            ::close(pty_fd);
        }
        return 1;
    }

    if (pty_fd != -1) {
        ::close(pty_fd);
    }
    return 0;
}
