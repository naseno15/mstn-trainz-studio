import QtQuick

// Center stage. Packages / Config / KUID / Export keep their widget page in the well.
// Texture Params and Mesh Lods paint the split (table + two previews) here.
// Texture Editor and Texture Denoiser paint one canvas well. The paint surface stays a widget.
Item {
    id: center

    readonly property color ink: bridge.dark ? "#f2f4f8" : "#1d1d1f"
    readonly property color mute: bridge.dark ? "#8b93a1" : "#5c6570"
    readonly property bool split: bridge.centerKind === "split"
    readonly property bool canvas: bridge.centerKind === "canvas"
    property real splitRatio: 0.46
    property real twinRatio: 0.5
    // Face inset + header. The widget page well starts under this.
    property real padTop: 22 + headCol.height + 8
    property real padSide: 16
    property real padBottom: 24

    function pageRoot() {
        var item = center
        while (item.parent)
            item = item.parent
        return item
    }

    function place(item, key) {
        if (!item.visible || item.width < 8 || item.height < 8) {
            bridge.placeWell(key, 0, 0, 0, 0)
            return
        }
        var p = item.mapToItem(pageRoot(), 0, 0)
        bridge.placeWell(key, p.x, p.y, item.width, item.height)
    }

    function syncWells() {
        place(tableSlot, "table")
        place(leftSlot, "left")
        place(rightSlot, "right")
        place(canvasSlot, "canvas")
    }

    FontLoader {
        id: mi
        source: bridge.iconFontUrl
    }

    GlassPlate {
        anchors.fill: parent
        dark: bridge.dark
        plateRadius: 16
        foot: 8

        Text {
            id: titleLab
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            text: bridge.centerTitle
            color: center.ink
            font.pixelSize: 16
            font.bold: true
            elide: Text.ElideRight
        }
        Text {
            id: tipLab
            anchors.top: titleLab.bottom
            anchors.topMargin: 6
            anchors.left: parent.left
            anchors.right: parent.right
            wrapMode: Text.WordWrap
            text: bridge.centerTip
            color: center.mute
            font.pixelSize: 12
            visible: text.length > 0
        }
        Item {
            id: headCol
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            height: titleLab.height + (tipLab.visible ? tipLab.height + 6 : 0)
        }

        Item {
            id: work
            anchors.top: headCol.bottom
            anchors.topMargin: 10
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            visible: center.split || center.canvas

            Item {
                id: tableBlock
                visible: center.split
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.right: parent.right
                height: center.split ? Math.max(80, (work.height - 36) * center.splitRatio) : 0

                Text {
                    id: listLab
                    anchors.top: parent.top
                    anchors.left: parent.left
                    anchors.right: parent.right
                    text: bridge.centerList
                    color: center.mute
                    font.pixelSize: 12
                    elide: Text.ElideRight
                }
                Item {
                    id: tableSlot
                    anchors.top: listLab.bottom
                    anchors.topMargin: 4
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    onXChanged: center.place(tableSlot, "table")
                    onYChanged: center.place(tableSlot, "table")
                    onWidthChanged: center.place(tableSlot, "table")
                    onHeightChanged: center.place(tableSlot, "table")
                }
            }

            MouseArea {
                visible: center.split
                z: 2
                anchors.left: parent.left
                anchors.right: parent.right
                y: tableBlock.height - 3
                height: 10
                cursorShape: Qt.SplitVCursor
                property real grabY: 0
                property real grabRatio: 0.46
                onPressed: {
                    grabY = mapToItem(work, 0, mouseY).y
                    grabRatio = center.splitRatio
                }
                onPositionChanged: {
                    if (!pressed)
                        return
                    var now = mapToItem(work, 0, mouseY).y
                    var span = Math.max(1, work.height - 36)
                    center.splitRatio = Math.max(0.22, Math.min(0.72, grabRatio + (now - grabY) / span))
                }
            }

            Item {
                id: previewBlock
                visible: center.split
                anchors.top: tableBlock.bottom
                anchors.topMargin: center.split ? 8 : 0
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom

                Item {
                    id: prevHead
                    anchors.top: parent.top
                    anchors.left: parent.left
                    anchors.right: parent.right
                    height: 28

                    Text {
                        anchors.left: parent.left
                        anchors.right: refreshBtn.left
                        anchors.rightMargin: 8
                        anchors.verticalCenter: parent.verticalCenter
                        text: bridge.centerPrev
                        color: center.mute
                        font.pixelSize: 12
                        elide: Text.ElideRight
                    }
                    RaiseButton {
                        id: refreshBtn
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        width: 32
                        height: 28
                        glyph: bridge.glyphRefresh
                        fontName: mi.name.length > 0 ? mi.name : bridge.iconFont
                        tip: "Refresh preview"
                        onClicked: bridge.refreshCenter()
                    }
                }

                Item {
                    id: leftSlot
                    anchors.top: prevHead.bottom
                    anchors.topMargin: 4
                    anchors.left: parent.left
                    anchors.bottom: parent.bottom
                    width: Math.max(40, (previewBlock.width - 8) * center.twinRatio)
                    onXChanged: center.place(leftSlot, "left")
                    onYChanged: center.place(leftSlot, "left")
                    onWidthChanged: center.place(leftSlot, "left")
                    onHeightChanged: center.place(leftSlot, "left")
                }

                MouseArea {
                    z: 2
                    anchors.top: prevHead.bottom
                    anchors.bottom: parent.bottom
                    x: leftSlot.width - 3
                    width: 10
                    cursorShape: Qt.SplitHCursor
                    property real grabX: 0
                    property real grabRatio: 0.5
                    onPressed: {
                        grabX = mapToItem(previewBlock, mouseX, 0).x
                        grabRatio = center.twinRatio
                    }
                    onPositionChanged: {
                        if (!pressed)
                            return
                        var now = mapToItem(previewBlock, mouseX, 0).x
                        var span = Math.max(1, previewBlock.width - 8)
                        center.twinRatio = Math.max(0.25, Math.min(0.75, grabRatio + (now - grabX) / span))
                    }
                }

                Item {
                    id: rightSlot
                    anchors.top: prevHead.bottom
                    anchors.topMargin: 4
                    anchors.left: leftSlot.right
                    anchors.leftMargin: 8
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    onXChanged: center.place(rightSlot, "right")
                    onYChanged: center.place(rightSlot, "right")
                    onWidthChanged: center.place(rightSlot, "right")
                    onHeightChanged: center.place(rightSlot, "right")
                }
            }

            Item {
                id: canvasSlot
                visible: center.canvas
                anchors.fill: parent
                onXChanged: center.place(canvasSlot, "canvas")
                onYChanged: center.place(canvasSlot, "canvas")
                onWidthChanged: center.place(canvasSlot, "canvas")
                onHeightChanged: center.place(canvasSlot, "canvas")
            }
        }
    }
}
