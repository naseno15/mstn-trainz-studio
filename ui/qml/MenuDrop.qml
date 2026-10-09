import QtQuick

Item {
    id: root

    Rectangle {
        id: card
        anchors.fill: parent
        transformOrigin: Item.Top
        scale: 0.94
        opacity: 0
        radius: 16
        color: bridge.dark ? Qt.rgba(0.10, 0.12, 0.16, 0.94) : Qt.rgba(0.96, 0.97, 0.98, 0.96)
        border.width: 1
        border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.18 : 0.8)

        Column {
            anchors.fill: parent
            anchors.margins: 6
            spacing: 2
            Repeater {
                model: bridge.items
                delegate: Item {
                    required property string actId
                    required property string label
                    required property string shortcut
                    required property bool sep
                    required property bool checked
                    required property bool alive
                    width: parent.width
                    height: sep ? 9 : 32

                    Rectangle {
                        visible: sep
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.leftMargin: 8
                        anchors.rightMargin: 8
                        height: 1
                        color: Qt.rgba(1, 1, 1, bridge.dark ? 0.12 : 0.35)
                    }

                    Rectangle {
                        visible: !sep
                        anchors.fill: parent
                        radius: 10
                        color: rowHover.hovered ? "#ff5a1f" : "transparent"
                        Behavior on color { ColorAnimation { duration: 110; easing.type: Easing.OutCubic } }
                        Row {
                            anchors.fill: parent
                            anchors.leftMargin: 10
                            anchors.rightMargin: 10
                            spacing: 8
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                text: checked ? "●" : ""
                                color: rowHover.hovered ? "#ffffff" : "#ff5a1f"
                                font.pixelSize: 10
                                width: 12
                            }
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                width: parent.width - 80
                                text: label
                                color: !alive
                                       ? "#888888"
                                       : (rowHover.hovered ? "#ffffff" : (bridge.dark ? "#f2f4f8" : "#1d1d1f"))
                                font.pixelSize: 13
                                elide: Text.ElideRight
                            }
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                text: shortcut
                                color: rowHover.hovered ? "#ffe8dc" : (bridge.dark ? "#9aa3b2" : "#6a7380")
                                font.pixelSize: 11
                            }
                        }
                        HoverHandler { id: rowHover; enabled: alive && !sep }
                        TapHandler {
                            enabled: alive && !sep
                            onTapped: bridge.triggerItem(actId)
                        }
                    }
                }
            }
        }
    }

    ParallelAnimation {
        id: pop
        NumberAnimation { target: card; property: "opacity"; from: 0; to: 1; duration: 140; easing.type: Easing.OutCubic }
        NumberAnimation { target: card; property: "scale"; from: 0.94; to: 1; duration: 170; easing.type: Easing.OutBack }
    }

    Connections {
        target: bridge
        function onMenuOpened() { pop.restart() }
    }
}
