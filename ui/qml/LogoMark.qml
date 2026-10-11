import QtQuick

// Cropped MSTN mark, centered in the parent width. `cap` is the longest edge of the ink.
Item {
    id: slot
    property real cap: 150
    width: parent ? parent.width : cap
    readonly property real markW: Math.min(cap, Math.max(1, width))
    height: markW * 0.45

    Image {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.verticalCenter: parent.verticalCenter
        width: slot.markW
        height: slot.height
        fillMode: Image.PreserveAspectFit
        sourceSize.width: 420
        source: "image://mstnlogo/" + (bridge.dark ? "dark" : "light")
    }
}
