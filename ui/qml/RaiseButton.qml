import QtQuick

// Raised glass button. Fields and tables use SunkField / a sunk well, not this.
Item {
    id: btn

    property string label: ""
    property string glyph: ""
    property string fontName: ""
    property string tip: ""
    property bool accent: false
    property bool lit: false
    signal clicked()

    function topItem() {
        var item = btn
        while (item.parent)
            item = item.parent
        return item
    }

    function shortTip(text) {
        var cut = text.indexOf(" — ")
        if (cut < 0)
            cut = text.indexOf(" – ")
        if (cut < 0)
            cut = text.indexOf(" - ")
        return cut < 0 ? text : text.slice(0, cut)
    }

    function placeTip() {
        if (tipItem.parent !== topItem())
            tipItem.parent = topItem()
        var root = tipItem.parent
        var above = btn.mapToItem(root, width / 2, 0)
        var below = btn.mapToItem(root, width / 2, height)
        var showBelow = above.y < tipItem.height + 10
        tipItem.caretDown = !showBelow
        tipItem.x = Math.max(8, Math.min(above.x - tipItem.width / 2, root.width - tipItem.width - 8))
        tipItem.y = showBelow ? below.y + 6 : above.y - tipItem.height - 4
        tipItem.caretX = above.x - tipItem.x
        tipItem.visible = true
    }

    implicitWidth: 88
    implicitHeight: 36

    Repeater {
        model: 3
        delegate: Rectangle {
            required property int index
            property real t: (index + 1) / 3
            anchors.fill: parent
            anchors.leftMargin: 2 - t * 3
            anchors.rightMargin: 2 - t * 3
            anchors.topMargin: 2 + index
            anchors.bottomMargin: -t * 3
            radius: 12
            color: Qt.rgba(0, 0, 0, (btn.accent || btn.lit ? 0.28 : 0.18) * (1.05 - t))
        }
    }

    Rectangle {
        id: face
        anchors.fill: parent
        anchors.bottomMargin: 3
        radius: 10
        border.width: 1
        border.color: btn.accent || btn.lit
                      ? Qt.rgba(1, 0.75, 0.6, 0.28)
                      : Qt.rgba(1, 1, 1, bridge.dark ? 0.12 : 0.40)
        gradient: Gradient {
            GradientStop {
                position: 0.0
                color: btn.accent || btn.lit ? "#e8683a" : (bridge.dark ? Qt.rgba(0.28, 0.31, 0.36, 0.96) : Qt.rgba(0.95, 0.96, 0.97, 0.96))
            }
            GradientStop {
                position: 0.40
                color: btn.accent || btn.lit ? "#d25424" : (bridge.dark ? Qt.rgba(0.18, 0.20, 0.24, 0.97) : Qt.rgba(0.88, 0.90, 0.93, 0.97))
            }
            GradientStop {
                position: 1.0
                color: btn.accent || btn.lit ? "#b84312" : (bridge.dark ? Qt.rgba(0.11, 0.12, 0.15, 0.98) : Qt.rgba(0.76, 0.79, 0.84, 0.98))
            }
        }
        Rectangle {
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.margins: 1
            height: parent.height * 0.45
            radius: 10
            gradient: Gradient {
                GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, btn.accent || btn.lit ? 0.16 : (bridge.dark ? 0.08 : 0.35)) }
                GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0) }
            }
        }
        Text {
            anchors.centerIn: parent
            text: btn.glyph.length > 0 ? btn.glyph : btn.label
            font.family: btn.glyph.length > 0 ? btn.fontName : ""
            font.pixelSize: btn.glyph.length > 0 ? 20 : 13
            font.bold: btn.glyph.length === 0
            color: btn.accent || btn.lit ? "#ffffff" : (bridge.dark ? "#f4f6fa" : "#1c1c1e")
        }
    }

    HoverHandler {
        id: hv
        onHoveredChanged: {
            if (hovered && btn.tip.length > 0) {
                tipWait.restart()
            } else {
                tipWait.stop()
                tipItem.visible = false
            }
        }
    }
    Timer {
        id: tipWait
        interval: 380
        onTriggered: if (hv.hovered && btn.tip.length > 0) btn.placeTip()
    }
    Rectangle {
        anchors.fill: face
        radius: 10
        color: hv.hovered ? Qt.rgba(1, 1, 1, 0.10) : "transparent"
    }
    TapHandler { onTapped: if (btn.enabled) btn.clicked() }

    // Reparented onto the page so sidebars and docks cannot clip it.
    Item {
        id: tipItem
        visible: false
        z: 4000
        width: tipText.width + 24
        height: tipText.height + 20
        property bool caretDown: true
        property real caretX: width / 2

        Text {
            id: tipText
            visible: false
            width: Math.min(220, implicitWidth)
            wrapMode: Text.WordWrap
            text: btn.shortTip(btn.tip)
            font.pixelSize: 12
        }
        Rectangle {
            id: caret
            width: 10
            height: 10
            rotation: 45
            x: tipItem.caretX - width / 2
            y: tipItem.caretDown ? tipItem.height - 12 : 2
            radius: 1
            color: bridge.dark ? "#242830" : "#f7f7f9"
            border.width: 1
            border.color: bridge.dark ? Qt.rgba(1, 1, 1, 0.28) : Qt.rgba(0, 0, 0, 0.12)
        }
        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: tipItem.caretDown ? parent.top : undefined
            anchors.bottom: tipItem.caretDown ? undefined : parent.bottom
            height: parent.height - 8
            radius: 10
            border.width: 1
            border.color: bridge.dark ? Qt.rgba(1, 1, 1, 0.28) : Qt.rgba(0, 0, 0, 0.12)
            gradient: Gradient {
                GradientStop { position: 0.0; color: bridge.dark ? "#2c323c" : "#ffffff" }
                GradientStop { position: 1.0; color: bridge.dark ? "#1a1e26" : "#f0f0f4" }
            }
            Text {
                anchors.fill: parent
                anchors.margins: 6
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                text: tipText.text
                color: bridge.dark ? "#f4f6fa" : "#1c1c1e"
                font.pixelSize: 12
                wrapMode: Text.WordWrap
            }
        }
    }
}
