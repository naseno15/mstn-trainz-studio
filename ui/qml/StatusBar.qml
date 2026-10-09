import QtQuick

// Footer: latest status line (click → LOGS sheet) · LOGS · VE.
Rectangle {
    id: root

    readonly property var inks: ({
        "save": "#30d158", "drop": "#ff5a1f", "progress": "#64d2ff", "error": "#ff453a", "info": "#8b93a1"
    })
    color: bridge.dark ? "#0f1217" : "#e6e9ee"

    Rectangle {
        anchors.top: parent.top
        width: parent.width
        height: 1
        color: Qt.rgba(1, 1, 1, bridge.dark ? 0.07 : 0.6)
    }

    component Pill: Rectangle {
        id: pill
        property string label: ""
        property string ink: ""
        signal pressed()
        width: pillText.implicitWidth + 18
        height: 20
        radius: 7
        anchors.verticalCenter: parent.verticalCenter
        color: pillHover.hovered ? Qt.rgba(1, 1, 1, bridge.dark ? 0.12 : 0.55) : Qt.rgba(1, 1, 1, bridge.dark ? 0.05 : 0.35)
        border.width: 1
        border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.10 : 0.6)
        Text {
            id: pillText
            anchors.centerIn: parent
            text: (typeof pill.label === "string" ? qsTr(pill.label) : pill.label)
            color: pill.ink.length ? pill.ink : (bridge.dark ? "#d6dae2" : "#2c2f36")
            font.pixelSize: 11
            font.bold: true
        }
        HoverHandler {
            id: pillHover
            cursorShape: Qt.PointingHandCursor
        }
        TapHandler { onTapped: pill.pressed() }
    }

    Row {
        anchors.left: parent.left
        anchors.right: right.left
        anchors.leftMargin: 12
        anchors.rightMargin: 12
        anchors.verticalCenter: parent.verticalCenter
        spacing: 8

        Rectangle {
            width: 7
            height: 7
            radius: 3.5
            anchors.verticalCenter: parent.verticalCenter
            visible: hub.text.length > 0
            color: root.inks[hub.textKind] || root.inks["info"]
        }
        Text {
            id: line
            width: parent.width - 15
            anchors.verticalCenter: parent.verticalCenter
            text: hub.text.length ? hub.text : qsTr("Ready")
            elide: Text.ElideRight
            color: hub.textKind === "error" ? "#ff6961" : (bridge.dark ? "#a8b0bc" : "#4a515c")
            font.pixelSize: 12
            HoverHandler { cursorShape: Qt.PointingHandCursor }
            TapHandler { onTapped: hub.openLog() }
        }
    }

    Row {
        id: right
        anchors.right: parent.right
        anchors.rightMargin: 10
        anchors.verticalCenter: parent.verticalCenter
        height: parent.height
        spacing: 6

        Pill {
            label: hub.logCount > 0 ? qsTr("LOGS ") + hub.logCount : qsTr("LOGS")
            onPressed: hub.openLog()
        }
        Pill {
            label: hub.veState === "bad" ? "VE!" : (hub.veState === "ok" ? qsTr("VE OK") : "VE")
            ink: hub.veState === "bad" ? "#ff453a" : (hub.veState === "ok" ? "#30d158" : "")
            onPressed: hub.openVe()
        }
    }
}
