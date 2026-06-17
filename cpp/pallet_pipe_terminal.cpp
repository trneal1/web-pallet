/*
 * pallet_pipe_terminal.cpp
 * ========================
 * Pipe text into an existing Web Pallet terminal region.
 *
 * Start the bridge and connect the browser first:
 *
 *     python3 python/bridge.py
 *
 * Then compile and run:
 *
 *     g++ -std=c++17 -O2 -Wall -Wextra -pedantic cpp/pallet_pipe_terminal.cpp -o pallet_pipe_terminal
 *     echo "hello" | ./pallet_pipe_terminal --id log
 *     some_command | ./pallet_pipe_terminal --id log --color "#86EFAC"
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
#include <sstream>
#include <stdexcept>
#include <string>
#include <sys/select.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <unistd.h>
#include <utility>

namespace {

constexpr const char* DEFAULT_BRIDGE_HOST = "127.0.0.1";
constexpr int DEFAULT_BRIDGE_PORT = 9000;

struct Args {
    std::string id = "default";
    std::string bridge_host = DEFAULT_BRIDGE_HOST;
    int bridge_port = DEFAULT_BRIDGE_PORT;
    std::optional<int> port;
    std::optional<std::string> color;
    std::optional<std::string> page;
    bool clear = false;
    bool define = false;
    int x = 24;
    int y = 24;
    int width = 700;
    int height = 300;
    std::string title;
    std::string background = "#020617";
    std::string text_color = "#E5E7EB";
    double timeout = 5.0;
};

[[noreturn]] void usage(int exit_code) {
    std::ostream& out = exit_code == 0 ? std::cout : std::cerr;
    out << "Usage: pallet_pipe_terminal [options]\n"
        << "\n"
        << "Write piped stdin lines to a Web Pallet terminal region.\n"
        << "\n"
        << "Options:\n"
        << "  --id ID                 terminal region id to write to (default: default)\n"
        << "  --bridge-host HOST      bridge TCP host or IP address (default: 127.0.0.1)\n"
        << "  --bridge-port PORT      bridge TCP port (default: 9000)\n"
        << "  --port PORT             alias for --bridge-port\n"
        << "  --color COLOR           optional CSS color for written text\n"
        << "  --page PAGE             pallet page to draw on\n"
        << "  --clear                 clear the terminal region before writing\n"
        << "  --define                define the terminal region before writing\n"
        << "  --x N                   region x position for --define (default: 24)\n"
        << "  --y N                   region y position for --define (default: 24)\n"
        << "  --width N               region width for --define (default: 700)\n"
        << "  --height N              region height for --define (default: 300)\n"
        << "  --title TEXT            region title for --define\n"
        << "  --background COLOR      region background color for --define (default: #020617)\n"
        << "  --text-color COLOR      region default text color for --define (default: #E5E7EB)\n"
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
        } else if (arg == "--color") {
            args.color = take_value(i, argc, argv, arg);
        } else if (arg == "--page") {
            args.page = take_value(i, argc, argv, arg);
        } else if (arg == "--clear") {
            args.clear = true;
        } else if (arg == "--define") {
            args.define = true;
        } else if (arg == "--x") {
            args.x = parse_int(take_value(i, argc, argv, arg), arg);
        } else if (arg == "--y") {
            args.y = parse_int(take_value(i, argc, argv, arg), arg);
        } else if (arg == "--width") {
            args.width = parse_int(take_value(i, argc, argv, arg), arg);
        } else if (arg == "--height") {
            args.height = parse_int(take_value(i, argc, argv, arg), arg);
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
                    out << "\\u";
                    const char* hex = "0123456789abcdef";
                    out << '0' << '0' << hex[(ch >> 4) & 0x0f] << hex[ch & 0x0f];
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

class PalletClient {
public:
    PalletClient(std::string host, int port, double timeout_seconds)
        : host_(std::move(host)), port_(port), timeout_seconds_(timeout_seconds) {}

    ~PalletClient() {
        close();
    }

    PalletClient(const PalletClient&) = delete;
    PalletClient& operator=(const PalletClient&) = delete;

    void connect() {
        struct addrinfo hints {};
        hints.ai_family = AF_UNSPEC;
        hints.ai_socktype = SOCK_STREAM;

        struct addrinfo* results = nullptr;
        const std::string port_text = std::to_string(port_);
        const int gai = getaddrinfo(host_.c_str(), port_text.c_str(), &hints, &results);
        if (gai != 0) {
            throw std::runtime_error("could not resolve bridge host " + host_ + ": " + gai_strerror(gai));
        }

        int last_errno = 0;
        for (struct addrinfo* rp = results; rp != nullptr; rp = rp->ai_next) {
            fd_ = socket(rp->ai_family, rp->ai_socktype, rp->ai_protocol);
            if (fd_ == -1) {
                last_errno = errno;
                continue;
            }

            if (connect_with_timeout(rp->ai_addr, rp->ai_addrlen)) {
                break;
            }

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

    void define_terminal_region(const Args& args) {
        std::ostringstream cmd;
        cmd << "{\"type\":\"terminal_define\""
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
            << ",\"font\":\"14px ui-monospace, SFMono-Regular, Consolas, monospace\""
            << ",\"padding\":8"
            << ",\"lineHeight\":18"
            << ",\"scrollback\":1000"
            << "}";
        command(cmd.str());
    }

    void clear_terminal(const std::string& id, const std::optional<std::string>& page) {
        std::string cmd = "{\"type\":\"terminal_clear\",\"id\":" + q(id);
        if (page) {
            cmd += ",\"page\":" + q(*page);
        }
        cmd += "}";
        command(cmd);
    }

    void write_terminal(const std::string& id, const std::string& text, const std::optional<std::string>& color, const std::optional<std::string>& page) {
        std::string cmd = "{\"type\":\"terminal_write\",\"id\":" + q(id) +
                          ",\"text\":" + q(text) +
                          ",\"newline\":true";
        if (color) {
            cmd += ",\"color\":" + q(*color);
        }
        if (page) {
            cmd += ",\"page\":" + q(*page);
        }
        cmd += "}";
        command(cmd);
    }

private:
    std::string host_;
    int port_;
    double timeout_seconds_;
    int fd_ = -1;
    std::string read_buffer_;

    bool connect_with_timeout(const struct sockaddr* addr, socklen_t len) {
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
                if (errno == EINTR) {
                    continue;
                }
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
                if (errno == EINTR) {
                    continue;
                }
                throw std::runtime_error("bridge read failed: " + std::string(std::strerror(errno)));
            }
            read_buffer_.append(buffer, static_cast<size_t>(received));
        }
    }

    void command(const std::string& json) {
        send_all(json + "\n");
        (void)read_line();
    }
};

std::string strip_line_ending(std::string line) {
    while (!line.empty() && (line.back() == '\n' || line.back() == '\r')) {
        line.pop_back();
    }
    return line;
}

}  // namespace

int main(int argc, char* argv[]) {
    try {
        Args args = parse_args(argc, argv);
        const int bridge_port = args.port.value_or(args.bridge_port);

        PalletClient pallet(args.bridge_host, bridge_port, args.timeout);
        pallet.connect();

        if (args.define) {
            pallet.define_terminal_region(args);
        }
        if (args.clear) {
            pallet.clear_terminal(args.id, args.page);
        }

        std::string line;
        while (std::getline(std::cin, line)) {
            pallet.write_terminal(args.id, strip_line_ending(line), args.color, args.page);
        }
    } catch (const std::exception& exc) {
        std::cerr << "Failed: " << exc.what() << "\n";
        return 1;
    }

    return 0;
}
