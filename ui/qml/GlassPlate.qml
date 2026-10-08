import QtQuick

// Raised or sunk frost plate.
// Floor shadow = several soft rings (cast onto the surface).
// Glass body = top shade + bottom lift so the plate itself has thickness.
Item {
    id: plate

    property bool dark: true
    property bool lit: false
    property bool sunk: false
    property real plateRadius: 22
    property real foot: 12
    default property alias content: body.data

    Repeater {
        model: plate.sunk ? 2 : 5
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
        id: face
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
                color: plate.sunk
                       ? (plate.dark ? Qt.rgba(0.07, 0.08, 0.10, 0.88) : Qt.rgba(0.86, 0.89, 0.93, 0.92))
                       : (plate.dark ? Qt.rgba(1, 1, 1, 0.16) : Qt.rgba(0.96, 0.97, 0.98, 0.90))
            }
            GradientStop {
                position: 0.22
                color: plate.dark
                       ? Qt.rgba(0.16, 0.18, 0.22, plate.sunk ? 0.92 : 0.86)
                       : Qt.rgba(0.90, 0.92, 0.95, 0.92)
            }
            GradientStop {
                position: 1.0
                color: plate.dark
                       ? Qt.rgba(0.06, 0.07, 0.09, 0.94)
                       : Qt.rgba(0.78, 0.82, 0.87, 0.94)
            }
        }

        // Short matte wash. No hard specular line.
        Rectangle {
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.margins: 1
            height: parent.height * 0.42
            radius: plate.plateRadius
            gradient: Gradient {
                GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, plate.dark ? 0.10 : 0.28) }
                GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0) }
            }
        }
    }

    Item {
        id: body
        anchors.fill: face
        anchors.margins: plate.sunk ? 10 : 14
    }
}
