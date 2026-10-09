import QtQuick

// DropArea that paints an orange dashed frame while files are dragged over it.
DropArea {
    id: zone
    z: 10
    // Cleared on drop so the frame is gone before the (blocking) load starts.
    property bool lit: false
    onEntered: lit = true
    onExited: lit = false
    signal filesDropped(var drop)
    onDropped: function (drop) {
        lit = false
        filesDropped(drop)
    }

    Rectangle {
        anchors.fill: parent
        radius: 8
        color: Qt.rgba(1, 0.353, 0.122, 0.10)
        visible: zone.lit && zone.enabled
    }

    Canvas {
        id: dash
        anchors.fill: parent
        visible: zone.lit && zone.enabled
        onVisibleChanged: if (visible) requestPaint()
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            ctx.strokeStyle = "#ff5a1f"
            ctx.lineWidth = 2
            ctx.setLineDash([6, 4])
            var r = 8, x = 2, y = 2, w = width - 4, h = height - 4
            ctx.beginPath()
            ctx.roundedRect(x, y, w, h, r, r)
            ctx.stroke()
        }
    }
}
