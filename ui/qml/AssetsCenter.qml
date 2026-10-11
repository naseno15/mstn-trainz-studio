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
    property bool quiet: false
    property bool freeze: false

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
        quiet: center.quiet
        freeze: center.freeze
        plateRadius: 16
        foot: 8

        Text {
            id: titleLab
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            text: (typeof bridge.centerTitle === "string" ? qsTr(bridge.centerTitle) : bridge.centerTitle)
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
            text: (typeof bridge.centerTip === "string" ? qsTr(bridge.centerTip) : bridge.centerTip)
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
                    text: (typeof bridge.centerList === "string" ? qsTr(bridge.centerList) : bridge.centerList)
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
                    property var rows: []
                    function reload() {
                        try { rows = JSON.parse(bridge.tableJson) }
                        catch (e) { rows = [] }
                    }
                    Connections {
                        target: bridge
                        function onChanged() { tableSlot.reload() }
                    }
                    Component.onCompleted: reload()
                    Rectangle {
                        anchors.fill: parent
                        radius: 12
                        color: Qt.rgba(0, 0, 0, bridge.dark ? 0.38 : 0.08)
                        border.width: 1
                        border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.12 : 0.40)
                    }
                    DropZone {
                        anchors.fill: parent
                        onFilesDropped: function (drop) { bridge.dropCenter(drop.urls) }
                    }
                    ListView {
                        id: fileList
                        anchors.fill: parent
                        clip: true
                        spacing: 4
                        model: tableSlot.rows
                        delegate: Rectangle {
                            required property var modelData
                            width: fileList.width
                            height: 36
                            radius: 8
                            color: modelData.on ? Qt.rgba(1, 0.35, 0.12, 0.28) : Qt.rgba(1, 1, 1, bridge.dark ? 0.05 : 0.45)
                            Text {
                                anchors.fill: parent
                                anchors.margins: 8
                                verticalAlignment: Text.AlignVCenter
                                text: (typeof modelData.text === "string" ? qsTr(modelData.text) : modelData.text)
                                color: bridge.dark ? "#f2f4f8" : "#1d1d1f"
                                font.pixelSize: 12
                                elide: Text.ElideRight
                            }
                            TapHandler { onTapped: bridge.pickCenter(modelData.row) }
                        }
                    }
                    Text {
                        anchors.centerIn: parent
                        visible: fileList.count === 0
                        width: parent.width - 24
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.WordWrap
                        text: bridge.page === "meshops" ? qsTr("Drop .trainzmesh, .im, or .fbx") : qsTr("Drop images")
                        color: center.mute
                        font.pixelSize: 13
                    }
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
                        text: (typeof bridge.centerPrev === "string" ? qsTr(bridge.centerPrev) : bridge.centerPrev)
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
                        tip: qsTr("Refresh preview")
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
                    Rectangle {
                        anchors.fill: parent
                        radius: 12
                        color: Qt.rgba(0, 0, 0, bridge.dark ? 0.38 : 0.08)
                        border.width: 1
                        border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.12 : 0.40)
                    }
                    Flickable {
                        anchors.fill: parent
                        anchors.margins: 8
                        clip: true
                        contentWidth: Math.max(width, leftText.implicitWidth)
                        contentHeight: leftText.implicitHeight
                        Text {
                            id: leftText
                            readonly property bool rich: bridge.wellLeft.length > 0
                            width: rich ? contentWidth : leftSlot.width - 16
                            wrapMode: rich ? Text.NoWrap : Text.Wrap
                            textFormat: rich ? Text.RichText : Text.PlainText
                            color: bridge.dark ? "#d4d4d4" : "#1d1d1f"
                            font.pixelSize: 12
                            font.family: "Consolas"
                            text: bridge.wellLeft.length > 0 ? bridge.wellLeft : qsTr("Preview")
                        }
                    }
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
                    Rectangle {
                        anchors.fill: parent
                        radius: 12
                        color: Qt.rgba(0, 0, 0, bridge.dark ? 0.38 : 0.08)
                        border.width: 1
                        border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.12 : 0.40)
                    }
                    Flickable {
                        anchors.fill: parent
                        anchors.margins: 8
                        clip: true
                        contentWidth: Math.max(width, rightText.implicitWidth)
                        contentHeight: rightText.implicitHeight
                        Text {
                            id: rightText
                            readonly property bool rich: bridge.wellRight.length > 0
                            width: rich ? contentWidth : rightSlot.width - 16
                            wrapMode: rich ? Text.NoWrap : Text.Wrap
                            textFormat: rich ? Text.RichText : Text.PlainText
                            color: bridge.dark ? "#d4d4d4" : "#3a414a"
                            font.pixelSize: 12
                            font.family: "Consolas"
                            text: bridge.wellRight.length > 0 ? bridge.wellRight : qsTr("Log")
                        }
                    }
                }
            }

                Item {
                    id: canvasSlot
                    visible: center.canvas
                    anchors.fill: parent
                    Rectangle {
                        anchors.fill: parent
                        radius: 12
                        color: Qt.rgba(0, 0, 0, bridge.dark ? 0.38 : 0.08)
                        border.width: 1
                        border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.12 : 0.40)
                    }
                    Text {
                        anchors.centerIn: parent
                        width: parent.width - 24
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.WordWrap
                        text: bridge.page === "denoise" ? qsTr("Open a bake from the right dock") : qsTr("Open a parameter map from the right dock")
                        color: center.mute
                        font.pixelSize: 13
                    }
                onXChanged: center.place(canvasSlot, "canvas")
                onYChanged: center.place(canvasSlot, "canvas")
                onWidthChanged: center.place(canvasSlot, "canvas")
                onHeightChanged: center.place(canvasSlot, "canvas")
            }
        }
    }
}
