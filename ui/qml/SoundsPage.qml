import QtQuick
import QtQuick.Layouts

Item {
    id: root

    readonly property color ink: bridge.dark ? "#f2f4f8" : "#1d1d1f"
    readonly property color mute: bridge.dark ? "#9aa3b2" : "#5c6570"
    readonly property color edge: Qt.rgba(1, 1, 1, 0.2)

    Rectangle {
        anchors.fill: parent
        color: bridge.dark ? "#12161c" : "#e4e9ef"
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 16
        spacing: 8

        RowLayout {
            Layout.fillWidth: true
            Text {
                text: (typeof bridge.title === "string" ? qsTr(bridge.title) : bridge.title)
                color: root.ink
                font.pixelSize: 18
                font.bold: true
            }
            Item { Layout.fillWidth: true }
            Rectangle {
                Layout.preferredWidth: ffLabel.implicitWidth + 28
                Layout.preferredHeight: 32
                radius: 10
                color: ffHover.hovered ? "#ff5a1f" : Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.70)
                border.color: root.edge
                border.width: 1
                Text {
                    id: ffLabel
                    anchors.centerIn: parent
                    text: (typeof bridge.ffmpegBtn === "string" ? qsTr(bridge.ffmpegBtn) : bridge.ffmpegBtn)
                    color: ffHover.hovered ? "#ffffff" : root.ink
                    font.pixelSize: 13
                }
                HoverHandler { id: ffHover }
                TapHandler { onTapped: bridge.pickFfmpeg() }
            }
        }

        Text {
            Layout.fillWidth: true
            text: (typeof bridge.ffmpeg === "string" ? qsTr(bridge.ffmpeg) : bridge.ffmpeg)
            color: root.mute
            font.pixelSize: 12
            elide: Text.ElideRight
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 8

            GlassPlate {
                dark: bridge.dark
                plateRadius: 16
                Layout.preferredWidth: 240
                Layout.fillHeight: true
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 8
                    Text { text: bridge.clipsTitle; color: root.ink; font.pixelSize: 13; font.bold: true }
                    ListView {
                        id: clips
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        model: bridge.clips
                        currentIndex: bridge.current
                        spacing: 2
                        delegate: Rectangle {
                            required property string modelData
                            required property int index
                            width: clips.width
                            height: 28
                            radius: 8
                            color: index === clips.currentIndex ? "#ff5a1f" : (rowHover.hovered ? Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.40) : "transparent")
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.left: parent.left
                                anchors.leftMargin: 8
                                anchors.right: parent.right
                                text: (typeof modelData === "string" ? qsTr(modelData) : modelData)
                                color: index === clips.currentIndex ? "#ffffff" : root.ink
                                font.pixelSize: 12
                                elide: Text.ElideRight
                            }
                            HoverHandler { id: rowHover }
                            TapHandler { onTapped: bridge.selectClip(index) }
                        }
                    }
                    Rectangle {
                        Layout.alignment: Qt.AlignHCenter
                        Layout.preferredWidth: 40
                        Layout.preferredHeight: 40
                        radius: 10
                        color: openHover.hovered ? "#ff5a1f" : (bridge.dark ? "#2a3340" : "#ffffff")
                        Text {
                            anchors.centerIn: parent
                            text: (typeof bridge.openGlyph === "string" ? qsTr(bridge.openGlyph) : bridge.openGlyph)
                            font.family: bridge.iconFont
                            font.pixelSize: 20
                            color: "#ff5a1f"
                        }
                        HoverHandler { id: openHover }
                        TapHandler { onTapped: bridge.browse() }
                    }
                    Text {
                        Layout.fillWidth: true
                        text: (typeof bridge.dropHint === "string" ? qsTr(bridge.dropHint) : bridge.dropHint)
                        color: root.mute
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                    }
                }
                DropZone {
                    anchors.fill: parent
                    onDropped: function (drop) {
                        var urls = []
                        for (var i = 0; i < drop.urls.length; ++i)
                            urls.push(String(drop.urls[i]))
                        bridge.dropUrls(urls)
                        drop.acceptProposedAction()
                    }
                }
            }

            GlassPlate {
                dark: bridge.dark
                plateRadius: 16
                Layout.fillWidth: true
                Layout.fillHeight: true
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 8
                    Text {
                        Layout.fillWidth: true
                        text: (typeof bridge.meta === "string" ? qsTr(bridge.meta) : bridge.meta)
                        color: root.mute
                        font.pixelSize: 12
                        elide: Text.ElideRight
                    }
                    Item {
                        id: waveSlot
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        function report() {
                            var p = mapToItem(root, 0, 0)
                            bridge.waveRect(p.x, p.y, width, height)
                        }
                        onWidthChanged: report()
                        onHeightChanged: report()
                        onXChanged: report()
                        onYChanged: report()
                        Component.onCompleted: report()
                    }
                    Text {
                        Layout.fillWidth: true
                        text: (typeof bridge.amp === "string" ? qsTr(bridge.amp) : bridge.amp)
                        color: root.mute
                        font.pixelSize: 12
                    }
                }
            }

            GlassPlate {
                dark: bridge.dark
                plateRadius: 16
                Layout.preferredWidth: 320
                Layout.fillHeight: true
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 8
                    Text { text: bridge.qcTitle; color: root.ink; font.pixelSize: 13; font.bold: true }
                    Flickable {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        contentWidth: width
                        contentHeight: qcText.implicitHeight
                        clip: true
                        Text {
                            id: qcText
                            width: parent.width
                            text: (typeof bridge.qc === "string" ? qsTr(bridge.qc) : bridge.qc)
                            color: root.ink
                            font.pixelSize: 12
                            font.family: "Consolas"
                            wrapMode: Text.WordWrap
                        }
                    }
                }
            }
        }

        GlassPlate {
            dark: bridge.dark
            plateRadius: 16
            foot: 6
            Layout.fillWidth: true
            Layout.preferredHeight: 72
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 10
                anchors.rightMargin: 10
                spacing: 8
                Repeater {
                    model: [
                        { label: bridge.setA, act: "a" },
                        { label: bridge.setB, act: "b" },
                        { label: bridge.playAB, act: "ab" }
                    ]
                    delegate: Rectangle {
                        required property var modelData
                        Layout.preferredWidth: lab.implicitWidth + 22
                        Layout.preferredHeight: 30
                        radius: 8
                        color: modelData.act === "ab" ? "#ff5a1f" : (h.hovered ? Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.35) : "transparent")
                        border.width: modelData.act === "ab" ? 0 : 1
                        border.color: root.edge
                        Text {
                            id: lab
                            anchors.centerIn: parent
                            text: (typeof modelData.label === "string" ? qsTr(modelData.label) : modelData.label)
                            color: modelData.act === "ab" ? "#ffffff" : root.ink
                            font.pixelSize: 13
                        }
                        HoverHandler { id: h }
                        TapHandler {
                            onTapped: {
                                if (modelData.act === "a") bridge.setSlotA()
                                else if (modelData.act === "b") bridge.setSlotB()
                                else bridge.playAB()
                            }
                        }
                    }
                }
                Text { text: bridge.slots; color: root.mute; font.pixelSize: 12; Layout.fillWidth: true; elide: Text.ElideRight }
                Text { text: bridge.phase; color: "#ff5a1f"; font.pixelSize: 12 }
            }
        }

        GlassPlate {
            dark: bridge.dark
            plateRadius: 16
            foot: 6
            Layout.fillWidth: true
            Layout.preferredHeight: 72
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 10
                anchors.rightMargin: 10
                spacing: 8
                Repeater {
                    model: [
                        { label: bridge.playLabel, act: "play", accent: false },
                        { label: bridge.stopLabel, act: "stop", accent: false },
                        { label: bridge.loopLabel, act: "loop", accent: false },
                        { label: bridge.fixLabel, act: "fix", accent: true }
                    ]
                    delegate: Rectangle {
                        required property var modelData
                        Layout.preferredWidth: t.implicitWidth + 22
                        Layout.preferredHeight: 30
                        radius: 8
                        color: modelData.accent ? "#ff5a1f" : (hh.hovered ? Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.35) : "transparent")
                        border.width: modelData.accent ? 0 : 1
                        border.color: root.edge
                        Text {
                            id: t
                            anchors.centerIn: parent
                            text: (typeof modelData.label === "string" ? qsTr(modelData.label) : modelData.label)
                            color: modelData.accent ? "#ffffff" : root.ink
                            font.pixelSize: 13
                        }
                        HoverHandler { id: hh }
                        TapHandler {
                            onTapped: {
                                if (modelData.act === "play") bridge.togglePlay()
                                else if (modelData.act === "stop") bridge.stop()
                                else if (modelData.act === "loop") bridge.toggleLoop()
                                else bridge.fix()
                            }
                        }
                    }
                }
                Rectangle {
                    Layout.preferredWidth: 36
                    Layout.preferredHeight: 30
                    radius: 8
                    color: "#ff5a1f"
                    Text {
                        anchors.centerIn: parent
                        text: (typeof bridge.saveGlyph === "string" ? qsTr(bridge.saveGlyph) : bridge.saveGlyph)
                        font.family: bridge.iconFont
                        font.pixelSize: 16
                        color: "#ffffff"
                    }
                    TapHandler { onTapped: bridge.saveAs() }
                }
                Text {
                    text: (typeof bridge.barTip === "string" ? qsTr(bridge.barTip) : bridge.barTip)
                    color: root.mute
                    font.pixelSize: 11
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }
            }
        }

        Rectangle {
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: homeLab.implicitWidth + 36
            Layout.preferredHeight: 36
            radius: 18
            color: homeHover.hovered ? "#ff5a1f" : Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.70)
            border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.22 : 0.75)
            border.width: 1
            Text {
                id: homeLab
                anchors.centerIn: parent
                text: (typeof bridge.homeLabel === "string" ? qsTr(bridge.homeLabel) : bridge.homeLabel)
                color: homeHover.hovered ? "#ffffff" : root.ink
                font.pixelSize: 13
                font.bold: true
            }
            HoverHandler { id: homeHover }
            TapHandler { onTapped: bridge.goHome() }
        }
    }
}
