import QtQuick

// Assets sidebar — logo, page title, action buttons. Packages queue is a widget in the well.
GlassPlate {
    id: side

    dark: bridge.dark
    plateRadius: 16
    foot: 8
    property real footPad: 0
    // Plate face + body inset. The queue widget is placed against the outer plate, so these keep it off the header and the buttons.
    readonly property real contentTop: 16
    readonly property real contentBottom: 24
    property real headH: contentTop + head.height + 10
    property real footH: contentBottom + foot.height + 14

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
                text: (typeof bridge.brand === "string" ? qsTr(bridge.brand) : bridge.brand)
                color: side.ink
                font.pixelSize: 15
                font.bold: true
            }
            Text {
                width: parent.width
                text: (typeof bridge.pageTitle === "string" ? qsTr(bridge.pageTitle) : bridge.pageTitle)
                color: side.ink
                font.pixelSize: 14
                font.bold: true
            }
            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                text: (typeof bridge.blurb === "string" ? qsTr(bridge.blurb) : bridge.blurb)
                color: side.mute
                font.pixelSize: 12
                visible: text.length > 0
            }
        }

        Item {
            id: queueWell
            visible: bridge.showQueue
            anchors.top: head.bottom
            anchors.bottom: foot.top
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.topMargin: 10
            anchors.bottomMargin: 8
            property var rows: []
            function parse() {
                try { return JSON.parse(bridge.suite === "texmesh" ? bridge.paramQueueJson : bridge.queueJson) }
                catch (e) { return [] }
            }
            Connections {
                target: bridge
                function onChanged() { queueWell.rows = queueWell.parse() }
            }
            Component.onCompleted: rows = parse()

            Rectangle {
                anchors.fill: parent
                radius: 12
                color: Qt.rgba(0, 0, 0, bridge.dark ? 0.38 : 0.08)
                border.width: 1
                border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.12 : 0.40)
            }
            Text {
                id: queueHead
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.margins: 8
                height: 16
                text: bridge.suite === "texmesh" ? qsTr("Maps") : qsTr("Kind     Name     Size     Info")
                color: side.mute
                font.pixelSize: 11
                font.bold: true
                elide: Text.ElideRight
            }

            DropZone {
                anchors.fill: parent
                onFilesDropped: function (drop) {
                    if (bridge.suite === "texmesh") bridge.dropCenter(drop.urls)
                    else bridge.dropPaths(drop.urls)
                }
            }

            ListView {
                id: queueList
                anchors.top: queueHead.bottom
                anchors.topMargin: 6
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.margins: 8
                clip: true
                spacing: 4
                boundsBehavior: Flickable.StopAtBounds
                model: queueWell.rows
                delegate: Rectangle {
                    required property var modelData
                    width: queueList.width
                    height: 48
                    radius: 10
                    color: modelData.on ? Qt.rgba(1, 0.35, 0.12, bridge.dark ? 0.28 : 0.18) : Qt.rgba(1, 1, 1, bridge.dark ? 0.05 : 0.45)
                    Column {
                        anchors.fill: parent
                        anchors.margins: 8
                        spacing: 2
                        Text {
                            width: parent.width
                            text: (typeof modelData.name === "string" ? qsTr(modelData.name) : modelData.name)
                            color: side.ink
                            font.pixelSize: 12
                            font.bold: true
                            elide: Text.ElideRight
                        }
                        Text {
                            width: parent.width
                            text: modelData.kind + qsTr("  ·  ") + modelData.size + qsTr("  ·  ") + modelData.info
                            color: side.mute
                            font.pixelSize: 11
                            elide: Text.ElideRight
                        }
                    }
                    TapHandler { onTapped: bridge.pickQueue(modelData.row) }
                }
            }

            Text {
                anchors.centerIn: parent
                visible: queueList.count === 0
                width: parent.width - 16
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                text: bridge.suite === "texmesh" ? qsTr("Drop images") : qsTr("Drop a CDP or a folder")
                color: side.mute
                font.pixelSize: 12
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

                Flow {
                    width: parent.width
                    spacing: 8
                    visible: iconRep.count > 0

                    Repeater {
                        id: iconRep
                        model: actionCol.icons()
                        delegate: Item {
                            required property var modelData
                            readonly property bool faced: (modelData.face || "").length > 0
                            width: faced ? Math.min(actionCol.width, 34 + faceMeasure.implicitWidth + 22) : 40
                            height: 40
                            Text {
                                id: faceMeasure
                                visible: false
                                text: modelData.face || ""
                                font.pixelSize: 12
                                font.bold: true
                            }
                            RaiseButton {
                                anchors.fill: parent
                                accent: !!modelData.accent
                                enabled: modelData.enabled !== false
                                opacity: enabled ? 1 : 0.4
                                glyph: modelData.glyph
                                label: modelData.face || ""
                                tip: modelData.tip || ""
                                fontName: mi.name.length > 0 ? mi.name : bridge.iconFont
                                onClicked: bridge.runAction(modelData.id)
                            }
                        }
                    }
                }

                Repeater {
                    model: actionCol.labels()
                    delegate: RaiseButton {
                        required property var modelData
                        width: actionCol.width
                        height: 40
                        label: (typeof modelData.label === "string" ? qsTr(modelData.label) : modelData.label)
                        accent: !!modelData.accent
                        enabled: modelData.enabled !== false
                        opacity: enabled ? 1 : 0.4
                        onClicked: bridge.runAction(modelData.id)
                    }
                }

                function rows() {
                    try { return JSON.parse(bridge.actionsJson) }
                    catch (e) { return [] }
                }
                function icons() {
                    return rows().filter(function (row) { return !!row.glyph })
                }
                function labels() {
                    return rows().filter(function (row) { return !row.glyph })
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
            Row {
                visible: bridge.showQueue
                spacing: 6

                Repeater {
                    model: {
                        try { return JSON.parse(bridge.queueBtnJson) }
                        catch (e) { return [] }
                    }
                    delegate: Item {
                        required property var modelData
                        width: 40
                        height: 40
                        RaiseButton {
                            anchors.fill: parent
                            glyph: modelData.glyph
                            tip: modelData.tip || ""
                            fontName: mi.name.length > 0 ? mi.name : bridge.iconFont
                            onClicked: modelData.id === "clear" ? bridge.queueClear() : bridge.queueRemove()
                        }
                    }
                }
            }
            Text {
                visible: bridge.showQueue
                text: (typeof bridge.footerCap === "string" ? qsTr(bridge.footerCap) : bridge.footerCap)
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
                    delegate: Item {
                        required property var modelData
                        width: 40
                        height: 40
                        RaiseButton {
                            anchors.fill: parent
                            accent: !!modelData.accent
                            glyph: modelData.glyph
                            tip: modelData.tip || ""
                            fontName: mi.name.length > 0 ? mi.name : bridge.iconFont
                            onClicked: bridge.runAction(modelData.id)
                        }
                    }
                }
            }
            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                text: (typeof bridge.footNote === "string" ? qsTr(bridge.footNote) : bridge.footNote)
                color: side.mute
                font.pixelSize: 11
            }
        }
    }
}
