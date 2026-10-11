import QtQuick

// Raised or sunk frost plate.
// Floor shadow = several soft rings (cast onto the surface).
// Glass body = top shade + bottom lift so the plate itself has thickness.
Item {
    id: plate

    property bool dark: true
    property bool lit: false
    property bool sunk: false
    property bool matte: false
    property bool quiet: false
    property bool freeze: false
    property real veil: 1
    readonly property real insetL: (sunk ? 0 : 2) + (sunk ? 10 : 14)
    readonly property real insetR: (sunk ? 0 : 2) + (sunk ? 10 : 14)
    readonly property real insetT: (sunk ? 2 : 1) + (sunk ? 10 : 14)
    readonly property real insetB: (sunk ? 1 : foot) + (sunk ? 10 : 14)
    readonly property real liveW: Math.max(0, width - insetL - insetR)
    readonly property real liveH: Math.max(0, height - insetT - insetB)
    property real freezeW: 0
    property real freezeH: 0
    onLiveWChanged: if (!freeze) freezeW = liveW
    onLiveHChanged: if (!freeze) freezeH = liveH
    clip: freeze
    property real plateRadius: 22
    property real foot: 12
    default property alias content: body.data

    Repeater {
        model: plate.quiet ? 0 : (plate.sunk ? 2 : 5)
        delegate: Rectangle {
            required property int index
            property real t: (index + 1) / (plate.sunk ? 2 : 5)
            property real spread: plate.sunk ? (4 + t * 6) : (6 + t * 14)
            anchors.fill: parent
            anchors.leftMargin: 8 - spread * 0.35
            anchors.rightMargin: 8 - spread * 0.35
            anchors.topMargin: plate.sunk ? 4 : (6 + index)
            anchors.bottomMargin: plate.sunk ? (2 - t * 2) : (1 - t * 3)
            radius: plate.plateRadius + spread * 0.25
            color: Qt.rgba(0, 0, 0, (plate.dark ? 0.22 : 0.10) * (1.05 - t) * (plate.lit ? 1.25 : 1.0))
        }
    }

    Rectangle {
        id: faceFlat
        visible: plate.quiet
        anchors.fill: parent
        anchors.leftMargin: plate.sunk ? 0 : 2
        anchors.rightMargin: plate.sunk ? 0 : 2
        anchors.topMargin: plate.sunk ? 2 : 1
        anchors.bottomMargin: plate.sunk ? 1 : plate.foot
        radius: plate.plateRadius
        color: plate.dark ? "#1e2430" : "#e7ebf1"
        border.width: 1
        border.color: Qt.rgba(1, 1, 1, plate.dark ? 0.08 : 0.40)
    }

    Rectangle {
        id: face
        visible: !plate.quiet
        anchors.fill: parent
        anchors.leftMargin: plate.sunk ? 0 : 2
        anchors.rightMargin: plate.sunk ? 0 : 2
        anchors.topMargin: plate.sunk ? 2 : 1
        anchors.bottomMargin: plate.sunk ? 1 : plate.foot
        radius: plate.plateRadius
        border.width: 1
        border.color: plate.lit
                      ? Qt.rgba(1, 0.45, 0.28, 0.45)
                      : Qt.rgba(1, 1, 1, plate.dark ? (plate.sunk ? 0.08 : 0.14) : 0.45)
        gradient: Gradient {
            GradientStop {
                position: 0.0
                color: plate.matte
                       ? (plate.dark ? Qt.rgba(0.16, 0.17, 0.20, 0.98) : Qt.rgba(0.94, 0.95, 0.97, 0.98))
                       : (plate.sunk
                          ? (plate.dark ? Qt.rgba(0.07, 0.08, 0.10, 0.55 * plate.veil) : Qt.rgba(0.86, 0.89, 0.93, 0.72 * plate.veil))
                          : (plate.dark ? Qt.rgba(1, 1, 1, 0.10 * plate.veil) : Qt.rgba(0.96, 0.97, 0.98, 0.55 * plate.veil)))
            }
            GradientStop {
                position: 0.22
                color: plate.matte
                       ? (plate.dark ? Qt.rgba(0.11, 0.12, 0.15, 0.99) : Qt.rgba(0.90, 0.92, 0.95, 0.99))
                       : (plate.dark
                          ? Qt.rgba(0.16, 0.18, 0.22, (plate.sunk ? 0.62 : 0.48) * plate.veil)
                          : Qt.rgba(0.90, 0.92, 0.95, 0.50 * plate.veil))
            }
            GradientStop {
                position: 1.0
                color: plate.matte
                       ? (plate.dark ? Qt.rgba(0.07, 0.08, 0.10, 1) : Qt.rgba(0.82, 0.85, 0.89, 1))
                       : (plate.dark
                          ? Qt.rgba(0.06, 0.07, 0.09, 0.58 * plate.veil)
                          : Qt.rgba(0.78, 0.82, 0.87, 0.55 * plate.veil))
            }
        }

        // Short matte wash. No hard specular line.
        Rectangle {
            visible: !plate.quiet
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.margins: 1
            height: parent.height * 0.42
            radius: plate.plateRadius
            gradient: Gradient {
                GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, plate.matte ? (plate.dark ? 0.05 : 0.16) : (plate.dark ? 0.10 : 0.28)) }
                GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0) }
            }
        }
    }

    Item {
        id: body
        x: plate.insetL
        y: plate.insetT
        // ponytail: while freeze is on, ignore the plate's live size so a splitter drag does not reflow the contents
        width: plate.freeze ? plate.freezeW : plate.liveW
        height: plate.freeze ? plate.freezeH : plate.liveH
    }
}
