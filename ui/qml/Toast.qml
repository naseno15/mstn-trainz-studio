import QtQuick

// Glass status chip under the title bar — save · drop · progress · error · info.
// Port of trainz_studio/ui/status_toast.py GlassToastBubble.
Item {
    id: root

    readonly property var marks: ({
        "save": ["✓", Qt.rgba(0.19, 0.82, 0.35, 0.22), "#30d158"],
        "drop": ["↓", Qt.rgba(1, 0.35, 0.12, 0.22), "#ff5a1f"],
        "progress": ["…", Qt.rgba(0.35, 0.78, 0.98, 0.22), "#64d2ff"],
        "error": ["×", Qt.rgba(1, 0.27, 0.23, 0.22), "#ff453a"],
        "info": ["i", Qt.rgba(1, 0.84, 0.04, 0.20), "#ffd60a"]
    })
    readonly property var mark: marks[hub.toastKind] || marks["info"]
    readonly property bool dark: bridge.dark

    Item {
        id: chip
        width: Math.min(root.width - 4, Math.max(300, row.implicitWidth + 30))
        height: col.implicitHeight + 22
        x: (root.width - width) / 2
        y: hub.toastShown ? 2 : -16
        opacity: hub.toastShown ? 1 : 0
        Behavior on y { NumberAnimation { duration: hub.toastShown ? 280 : 200; easing.type: hub.toastShown ? Easing.OutCubic : Easing.InCubic } }
        Behavior on opacity { NumberAnimation { duration: hub.toastShown ? 240 : 180; easing.type: Easing.OutCubic } }

        // Kind-tinted bloom behind the plate.
        Rectangle {
            anchors.fill: parent
            anchors.margins: -6
            radius: 18
            color: "transparent"
            border.width: 6
            border.color: Qt.rgba(Qt.color(root.mark[2]).r, Qt.color(root.mark[2]).g, Qt.color(root.mark[2]).b, root.dark ? 0.07 : 0.05)
        }
        Repeater {
            model: 4
            delegate: Rectangle {
                required property int index
                property real t: (index + 1) / 4
                anchors.fill: parent
                anchors.leftMargin: 2 - t * 4
                anchors.rightMargin: 2 - t * 4
                anchors.topMargin: 2 + index * 0.5
                anchors.bottomMargin: -t * 5
                radius: 12 + t * 2
                color: Qt.rgba(0, 0, 0, (root.dark ? 0.16 : 0.07) * (1.05 - t))
            }
        }
        Rectangle {
            anchors.fill: parent
            radius: 12
            border.width: 1
            border.color: Qt.rgba(1, 1, 1, root.dark ? 0.19 : 0.63)
            gradient: Gradient {
                GradientStop { position: 0.0; color: root.dark ? Qt.rgba(48 / 255, 54 / 255, 64 / 255, 0.82) : Qt.rgba(246 / 255, 248 / 255, 251 / 255, 0.90) }
                GradientStop { position: 1.0; color: root.dark ? Qt.rgba(16 / 255, 20 / 255, 26 / 255, 0.90) : Qt.rgba(220 / 255, 226 / 255, 234 / 255, 0.92) }
            }
        }

        Column {
            id: col
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.leftMargin: 14
            anchors.rightMargin: 16
            anchors.topMargin: 10
            spacing: 6

            Row {
                id: row
                spacing: 8
                width: parent.width

                Rectangle {
                    width: 18
                    height: 18
                    radius: 6
                    anchors.verticalCenter: parent.verticalCenter
                    color: root.mark[1]
                    Text {
                        anchors.centerIn: parent
                        text: root.mark[0]
                        color: root.mark[2]
                        font.pixelSize: 10
                        font.bold: true
                    }
                }
                Column {
                    spacing: 1
                    width: Math.min(420, Math.max(220, title.implicitWidth, detail.implicitWidth))
                    Text {
                        id: title
                        width: parent.width
                        text: (typeof hub.toastTitle === "string" ? qsTr(hub.toastTitle) : hub.toastTitle)
                        elide: Text.ElideRight
                        color: root.dark ? "#f5f5f7" : "#1d1d1f"
                        font.pixelSize: 12
                        font.weight: Font.DemiBold
                    }
                    Text {
                        id: detail
                        width: parent.width
                        visible: text.length > 0
                        text: (typeof hub.toastDetail === "string" ? qsTr(hub.toastDetail) : hub.toastDetail)
                        elide: Text.ElideRight
                        color: root.dark ? Qt.rgba(235 / 255, 235 / 255, 245 / 255, 0.62) : Qt.rgba(29 / 255, 29 / 255, 31 / 255, 0.58)
                        font.pixelSize: 12
                        font.weight: Font.Medium
                    }
                }
                Text {
                    visible: hub.toastPct >= 0
                    width: 36
                    anchors.verticalCenter: parent.verticalCenter
                    horizontalAlignment: Text.AlignRight
                    text: hub.toastPct + "%"
                    color: detail.color
                    font.pixelSize: 12
                    font.weight: Font.Medium
                }
            }

            Rectangle {
                visible: hub.toastPct >= 0
                width: parent.width
                height: 2
                radius: 1
                color: Qt.rgba(0.5, 0.5, 0.5, 0.22)
                Rectangle {
                    width: parent.width * Math.max(0, hub.toastPct) / 100
                    height: parent.height
                    radius: 1
                    color: "#64d2ff"
                    Behavior on width { NumberAnimation { duration: 120 } }
                }
            }
        }
    }
}
