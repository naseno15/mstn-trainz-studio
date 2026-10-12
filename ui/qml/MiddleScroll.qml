import QtQuick

// Middle-button drag scrolls `flick` at `gain`× the pointer travel. Left clicks still reach the rows.
DragHandler {
    required property Flickable flick
    property real gain: 3
    property real lastY: 0
    target: null
    acceptedButtons: Qt.MiddleButton
    cursorShape: Qt.ClosedHandCursor
    onActiveChanged: lastY = centroid.scenePosition.y
    onCentroidChanged: {
        if (!active)
            return
        var y = centroid.scenePosition.y
        flick.contentY = Math.max(0, Math.min(flick.contentHeight - flick.height, flick.contentY - (y - lastY) * gain))
        lastY = y
    }
}
