// TGA for every QImage / QImageReader / QImage::save / QML Image in the app.
// The Qt builds used here ship no qtga plugin, and Qt's own one cannot write.
// Built with QT_STATICPLUGIN (see CMakeLists.txt) and registered below.
#include <QIODevice>
#include <QImage>
#include <QImageIOHandler>
#include <QImageIOPlugin>
#include <QSize>
#include <QVariant>
#include <QtPlugin>

namespace {

struct TgaHeader {
    int idlen = 0;
    int type = 0;
    int w = 0;
    int h = 0;
    int bpp = 0;
    int desc = 0;
};

// strict: also require an empty colour-map spec, for sniffing files without a .tga suffix.
bool read_header(const QByteArray& head, TgaHeader* out, bool strict) {
    if (head.size() < 18) return false;
    const auto* d = reinterpret_cast<const uchar*>(head.constData());
    TgaHeader h;
    h.idlen = d[0];
    h.type = d[2];
    h.w = d[12] | (d[13] << 8);
    h.h = d[14] | (d[15] << 8);
    h.bpp = d[16];
    h.desc = d[17];
    const bool color = (h.type == 2 || h.type == 10) && (h.bpp == 24 || h.bpp == 32);
    const bool gray = (h.type == 3 || h.type == 11) && h.bpp == 8;
    if (d[1] != 0 || !(color || gray) || h.w < 1 || h.h < 1) return false;
    if (strict && (d[3] | d[4] | d[5] | d[6] | d[7])) return false;
    *out = h;
    return true;
}

QImage decode(const QByteArray& bytes) {
    TgaHeader h;
    if (!read_header(bytes, &h, false)) return {};
    const int pp = h.bpp / 8;
    const auto* s = reinterpret_cast<const uchar*>(bytes.constData()) + 18 + h.idlen;
    const auto* end = reinterpret_cast<const uchar*>(bytes.constData()) + bytes.size();
    if (s > end) return {};
    QImage img(h.w, h.h, pp == 1 ? QImage::Format_Grayscale8 : pp == 3 ? QImage::Format_RGB888 : QImage::Format_RGBA8888);
    if (img.isNull()) return {};
    auto put = [&](qint64 i, const uchar* px) {
        int x = static_cast<int>(i % h.w);
        int y = static_cast<int>(i / h.w);
        if (h.desc & 0x10) x = h.w - 1 - x;
        if (!(h.desc & 0x20)) y = h.h - 1 - y;
        uchar* p = img.scanLine(y) + x * pp;
        if (pp == 1) {
            p[0] = px[0];
            return;
        }
        p[0] = px[2];
        p[1] = px[1];
        p[2] = px[0];
        if (pp == 4) p[3] = px[3];
    };
    const qint64 pixels = static_cast<qint64>(h.w) * h.h;
    if (h.type == 2 || h.type == 3) {
        if (end - s < pixels * pp) return {};
        for (qint64 i = 0; i < pixels; ++i) put(i, s + i * pp);
        return img;
    }
    qint64 i = 0;
    while (i < pixels && s < end) {
        const uchar packet = *s++;
        const int count = (packet & 0x7f) + 1;
        if (packet & 0x80) {
            if (end - s < pp) return {};
            for (int k = 0; k < count && i < pixels; ++k) put(i++, s);
            s += pp;
        } else {
            if (end - s < static_cast<qint64>(count) * pp) return {};
            for (int k = 0; k < count && i < pixels; ++k, s += pp) put(i++, s);
        }
    }
    return i == pixels ? img : QImage();
}

// Uncompressed, bottom-left origin: 8-bit grey, 24-bit BGR, or 32-bit BGRA when the image has alpha.
QByteArray encode(const QImage& src) {
    if (src.isNull() || src.width() > 0xffff || src.height() > 0xffff) return {};
    const bool gray = src.format() == QImage::Format_Grayscale8;
    const bool alpha = !gray && src.hasAlphaChannel();
    const int pp = gray ? 1 : alpha ? 4 : 3;
    const QImage img = src.convertToFormat(gray ? QImage::Format_Grayscale8 : alpha ? QImage::Format_RGBA8888 : QImage::Format_RGB888);
    QByteArray out(18, '\0');
    out[2] = static_cast<char>(gray ? 3 : 2);
    out[12] = static_cast<char>(img.width() & 0xff);
    out[13] = static_cast<char>(img.width() >> 8);
    out[14] = static_cast<char>(img.height() & 0xff);
    out[15] = static_cast<char>(img.height() >> 8);
    out[16] = static_cast<char>(pp * 8);
    out[17] = static_cast<char>(alpha ? 8 : 0);
    out.reserve(18 + img.width() * img.height() * pp);
    for (int y = img.height() - 1; y >= 0; --y) {
        const uchar* row = img.constScanLine(y);
        for (int x = 0; x < img.width(); ++x) {
            const uchar* p = row + x * pp;
            if (pp == 1) {
                out.append(static_cast<char>(p[0]));
                continue;
            }
            out.append(static_cast<char>(p[2]));
            out.append(static_cast<char>(p[1]));
            out.append(static_cast<char>(p[0]));
            if (pp == 4) out.append(static_cast<char>(p[3]));
        }
    }
    return out;
}

class TgaHandler final : public QImageIOHandler {
public:
    static bool sniff(QIODevice* device) {
        TgaHeader h;
        return device && read_header(device->peek(18), &h, true);
    }
    bool canRead() const override {
        TgaHeader h;
        if (!device() || !read_header(device()->peek(18), &h, false)) return false;
        setFormat("tga");
        return true;
    }
    bool read(QImage* image) override {
        *image = decode(device()->readAll());
        return !image->isNull();
    }
    bool write(const QImage& image) override {
        const QByteArray out = encode(image);
        return !out.isEmpty() && device()->write(out) == out.size();
    }
    bool supportsOption(ImageOption option) const override { return option == Size; }
    QVariant option(ImageOption option) const override {
        TgaHeader h;
        if (option != Size || !device() || !read_header(device()->peek(18), &h, false)) return {};
        return QSize(h.w, h.h);
    }
};

}  // namespace

class TrainzTgaPlugin final : public QImageIOPlugin {
    Q_OBJECT
    Q_PLUGIN_METADATA(IID QImageIOHandlerFactoryInterface_iid FILE "tga_image.json")

public:
    Capabilities capabilities(QIODevice* device, const QByteArray& format) const override {
        if (format.compare("tga", Qt::CaseInsensitive) == 0) return CanRead | CanWrite;
        if (!format.isEmpty() || !device || !device->isOpen() || !device->isReadable()) return {};
        return TgaHandler::sniff(device) ? CanRead : Capabilities();
    }
    QImageIOHandler* create(QIODevice* device, const QByteArray& format) const override {
        auto* handler = new TgaHandler;
        handler->setDevice(device);
        handler->setFormat(format.isEmpty() ? QByteArray("tga") : format);
        return handler;
    }
};

#include "tga_image.moc"

Q_IMPORT_PLUGIN(TrainzTgaPlugin)
