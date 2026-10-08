import QtQuick

// Glass tip with a caret. Same language as the widget GlassTipBubble, aimed at an icon.
Item {
    id: tip

    property string text: ""
    property bool dark: true
    readonly property int padX: 12
    readonly property int padY: 7
    readonly property int caret: 7

    visible: text.length > 0
    z: 80
    width: body.width + caret
    height: body.height

    property var anchorItem: null

    function showFor(item, message) {
        text = message || ""
        anchorItem = item
        if (text.length === 0)
            return
        Qt.callLater(place)
    }

    function place() {
        if (!anchorItem || text.length === 0 || !parent)
            return
        var p = anchorItem.mapToItem(parent, anchorItem.width + 8, anchorItem.height / 2)
        x = p.x
        y = Math.max(6, Math.min(p.y - height / 2, parent.height - height - 6))
    }

    function hide() {
        text = ""
        anchorItem = null
    }

    Rectangle {
        id: nib
        width: 10
        height: 10
        rotation: 45
        x: 2
        anchors.verticalCenter: parent.verticalCenter
        color: tip.dark ? "#242830" : "#f4f4f6"
        border.width: 1
        border.color: tip.dark ? Qt.rgba(1, 1, 1, 0.22) : Qt.rgba(0, 0, 0, 0.12)
    }

    Rectangle {
        id: body
        x: tip.caret
        width: label.width + tip.padX * 2
        height: label.height + tip.padY * 2
        radius: 10
        border.width: 1
        border.color: tip.dark ? Qt.rgba(1, 1, 1, 0.22) : Qt.rgba(0, 0, 0, 0.12)
        gradient: Gradient {
            GradientStop { position: 0.0; color: tip.dark ? "#2a3038" : "#ffffff" }
            GradientStop { position: 0.55; color: tip.dark ? "#22262c" : "#f7f7f9" }
            GradientStop { position: 1.0; color: tip.dark ? "#1a1e24" : "#efeff2" }
        }

        Text {
            id: label
            x: tip.padX
            y: tip.padY
            width: Math.min(216, implicitWidth)
            wrapMode: Text.WordWrap
            text: tip.text
            color: tip.dark ? "#f4f6fa" : "#1c1c1e"
            font.pixelSize: 12
        }
    }
}
