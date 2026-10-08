import QtQuick

// Assets sidebar — logo, page title, action buttons. Packages queue is a widget in the well.
GlassPlate {
    id: side

    dark: bridge.dark
    plateRadius: 16
    foot: 8
    property real footPad: 0
    property real headH: head.height + 8
    property real footH: foot.height + 8

    readonly property color ink: bridge.dark ? "#f2f4f8" : "#1d1d1f"
    readonly property color mute: bridge.dark ? "#8b93a1" : "#5c6570"

    FontLoader {
        id: mi
        source: bridge.iconFontUrl
    }

    Item {
        anchors.fill: parent

        Column {
            id: head
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            spacing: 6

            Image {
                anchors.horizontalCenter: parent.horizontalCenter
                width: 108
                height: 36
                fillMode: Image.PreserveAspectFit
                source: bridge.dark ? "image://mstnlogo/dark" : "image://mstnlogo/light"
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                text: bridge.brand
                color: side.ink
                font.pixelSize: 15
                font.bold: true
            }
            Text {
                width: parent.width
                text: bridge.pageTitle
                color: side.ink
                font.pixelSize: 14
                font.bold: true
            }
            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                text: bridge.blurb
                color: side.mute
                font.pixelSize: 12
                visible: text.length > 0
            }
        }

        Flickable {
            id: actions
            visible: !bridge.showQueue
            anchors.top: head.bottom
            anchors.bottom: foot.top
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.topMargin: 10
            anchors.bottomMargin: 8
            contentHeight: actionCol.height
            clip: true
            boundsBehavior: Flickable.StopAtBounds

            Column {
                id: actionCol
                width: parent.width
                spacing: 8

                Repeater {
                    model: {
                        try { return JSON.parse(bridge.actionsJson) }
                        catch (e) { return [] }
                    }
                    delegate: RaiseButton {
                        required property var modelData
                        width: actionCol.width
                        height: 40
                        label: modelData.label
                        accent: !!modelData.accent
                        enabled: modelData.enabled !== false
                        opacity: enabled ? 1 : 0.4
                        onClicked: bridge.runAction(modelData.id)
                    }
                }
            }
        }

        Column {
            id: foot
            anchors.bottom: parent.bottom
            anchors.bottomMargin: side.footPad
            anchors.left: parent.left
            anchors.right: parent.right
            spacing: 6

            Rectangle {
                width: parent.width
                height: 1
                color: Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.35)
            }
            Text {
                visible: bridge.showQueue
                text: bridge.footerCap
                color: side.mute
                font.pixelSize: 11
                font.bold: true
            }
            Row {
                visible: bridge.showQueue
                spacing: 6
                anchors.horizontalCenter: parent.horizontalCenter

                Repeater {
                    model: {
                        try { return JSON.parse(bridge.footerJson) }
                        catch (e) { return [] }
                    }
                    delegate: RaiseButton {
                        required property var modelData
                        width: 40
                        height: 40
                        accent: !!modelData.accent
                        glyph: modelData.glyph
                        fontName: mi.name.length > 0 ? mi.name : bridge.iconFont
                        onClicked: bridge.runAction(modelData.id)
                    }
                }
            }
            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                text: bridge.footNote
                color: side.mute
                font.pixelSize: 11
            }
        }
    }
}
