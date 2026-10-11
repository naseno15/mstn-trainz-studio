import QtQuick

// Update sheet. Opens on the GitHub check, then lists releases you can expand.
Item {
    id: root

    readonly property string heading: upd.checking ? qsTr("Checking for updates…")
            : upd.error.length > 0 && upd.releases.length === 0 ? qsTr("Could not check for updates")
            : upd.newer ? qsTr("Update available")
            : qsTr("Trainz Studio is up to date")

    Rectangle {
        id: scrim
        anchors.fill: parent
        color: Qt.rgba(0.04, 0.05, 0.07, upd.dark ? 0.62 : 0.42)
        opacity: 0
        MouseArea { anchors.fill: parent }
        Component.onCompleted: opacity = 1
        Behavior on opacity { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
    }

    GlassPlate {
        id: card
        anchors.centerIn: parent
        anchors.verticalCenterOffset: rise
        width: Math.min(560, parent.width - 48)
        height: Math.min(upd.checking ? 280 : 540, parent.height - 48)
        dark: upd.dark
        matte: true
        plateRadius: 18
        opacity: 0
        scale: 0.96
        property real rise: 18
        Component.onCompleted: { rise = 0; scale = 1; opacity = 1 }
        Behavior on rise { NumberAnimation { duration: 240; easing.type: Easing.OutCubic } }
        Behavior on scale { NumberAnimation { duration: 240; easing.type: Easing.OutCubic } }
        Behavior on opacity { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }

        Column {
            anchors.fill: parent
            spacing: 10

            Row {
                width: parent.width
                spacing: 12
                Rectangle {
                    width: 40
                    height: 40
                    radius: 12
                    color: Qt.rgba(1, 0.35, 0.12, 0.18)
                    Text {
                        anchors.centerIn: parent
                        text: upd.checking ? "" : upd.newer ? "↑" : upd.error.length > 0 && upd.releases.length === 0 ? "!" : "✓"
                        color: "#ff5a1f"
                        font.pixelSize: 18
                        font.bold: true
                    }
                    Canvas {
                        id: spin
                        anchors.centerIn: parent
                        width: 22
                        height: 22
                        visible: upd.checking
                        onPaint: {
                            var ctx = getContext("2d")
                            ctx.reset()
                            ctx.strokeStyle = "#ff5a1f"
                            ctx.lineWidth = 2.5
                            ctx.lineCap = "round"
                            ctx.beginPath()
                            ctx.arc(width / 2, height / 2, 8, 0, Math.PI * 1.35)
                            ctx.stroke()
                        }
                        RotationAnimation on rotation {
                            from: 0
                            to: 360
                            duration: 800
                            loops: Animation.Infinite
                            running: upd.checking
                        }
                    }
                }
                Column {
                    width: parent.width - 52
                    spacing: 2
                    Text {
                        width: parent.width
                        text: root.heading
                        color: upd.dark ? "#f2f3f5" : "#1d1d1f"
                        font.pixelSize: 16
                        font.bold: true
                        wrapMode: Text.WordWrap
                    }
                    Text {
                        width: parent.width
                        text: upd.checking ? qsTr("Contacting GitHub…") : qsTr("This copy") + "  " + upd.currentVersion
                        color: upd.dark ? "#a8b0bc" : "#5c6570"
                        font.pixelSize: 12
                    }
                }
            }

            Text {
                visible: !upd.checking && upd.version.length > 0
                width: parent.width
                text: qsTr("Latest release") + "  " + upd.version
                color: upd.dark ? "#d5d8e0" : "#1d1d1f"
                font.pixelSize: 13
            }
            Text {
                visible: !upd.checking && upd.commitSha.length > 0
                width: parent.width
                wrapMode: Text.WordWrap
                text: qsTr("Latest commit") + "  " + upd.commitSha + "  ·  " + upd.commitWhen + "\n" + upd.commitTitle
                color: upd.dark ? "#a8b0bc" : "#5c6570"
                font.pixelSize: 12
            }
            Text {
                visible: upd.newer && !upd.busy
                width: parent.width
                wrapMode: Text.WordWrap
                text: qsTr("This copy will close, replace the files in this folder, and open again.")
                color: upd.dark ? "#d5d8e0" : "#1d1d1f"
                font.pixelSize: 12
            }
            Text {
                visible: upd.newer
                width: parent.width
                text: upd.folder
                elide: Text.ElideMiddle
                color: upd.dark ? "#8b93a1" : "#5c6570"
                font.pixelSize: 11
            }

            Flickable {
                id: scroller
                visible: !upd.checking && upd.releases.length > 0
                width: parent.width
                height: Math.max(120, card.height - 250)
                contentHeight: list.height
                clip: true
                flickableDirection: Flickable.VerticalFlick

                Column {
                    id: list
                    width: scroller.width
                    spacing: 6
                    Repeater {
                        model: upd.releases
                        delegate: Rectangle {
                            id: row
                            required property var modelData
                            required property int index
                            width: list.width
                            height: block.height + 12
                            radius: 10
                            color: upd.dark ? Qt.rgba(1, 1, 1, 0.05) : Qt.rgba(0, 0, 0, 0.04)
                            property bool open: index === 0
                            property bool live: false
                            Component.onCompleted: Qt.callLater(function() { live = true })

                            Column {
                                id: block
                                x: 10
                                y: 6
                                width: parent.width - 20
                                spacing: 4
                                Row {
                                    width: parent.width
                                    spacing: 8
                                    Text {
                                        text: "▸"
                                        color: "#ff5a1f"
                                        font.pixelSize: 12
                                        rotation: row.open ? 90 : 0
                                        transformOrigin: Item.Center
                                        Behavior on rotation { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
                                    }
                                    Text {
                                        width: parent.width - 20
                                        text: modelData.version + (modelData.installed ? "  ·  " + qsTr("Installed") : modelData.newer ? "  ·  " + qsTr("Update available") : "") + "    " + modelData.when
                                        color: upd.dark ? "#f2f3f5" : "#1d1d1f"
                                        font.pixelSize: 12
                                        font.bold: true
                                        elide: Text.ElideRight
                                    }
                                }
                                Item {
                                    width: parent.width
                                    clip: true
                                    height: row.open ? notesText.implicitHeight : 0
                                    Behavior on height {
                                        enabled: row.live
                                        NumberAnimation { duration: 180; easing.type: Easing.OutCubic }
                                    }
                                    Text {
                                        id: notesText
                                        width: parent.width
                                        wrapMode: Text.WordWrap
                                        text: modelData.notes.length > 0 ? modelData.notes : qsTr("No notes for this release")
                                        color: upd.dark ? "#c5cad3" : "#3a4150"
                                        font.pixelSize: 12
                                    }
                                }
                            }
                            MouseArea {
                                anchors.fill: parent
                                onClicked: row.open = !row.open
                            }
                        }
                    }
                }
            }

            Rectangle {
                visible: upd.busy
                width: parent.width
                height: 4
                radius: 2
                color: Qt.rgba(0.5, 0.5, 0.5, 0.22)
                Rectangle {
                    width: upd.pct >= 0 ? parent.width * upd.pct / 100 : parent.width * 0.3
                    height: parent.height
                    radius: 2
                    color: "#ff5a1f"
                }
            }
            Text {
                visible: upd.busy
                text: upd.pct >= 0 ? qsTr("Downloading update…") + "  " + upd.pct + "%" : qsTr("Downloading update…")
                color: upd.dark ? "#a8b0bc" : "#5c6570"
                font.pixelSize: 12
            }
            Text {
                visible: upd.error.length > 0
                width: parent.width
                wrapMode: Text.WordWrap
                text: qsTr(upd.error)
                color: "#ff453a"
                font.pixelSize: 12
            }

            Item { width: 1; height: 1 }

            Row {
                width: parent.width
                spacing: 8
                RaiseButton {
                    label: upd.newer ? qsTr("Later") : qsTr("Close")
                    width: 120
                    onClicked: upd.later()
                }
                Item { width: Math.max(0, parent.width - 120 - (upd.newer ? 188 : 0)); height: 1 }
                RaiseButton {
                    visible: upd.newer
                    label: qsTr("Install update")
                    accent: true
                    width: upd.newer ? 180 : 0
                    enabled: !upd.busy && !upd.checking
                    onClicked: upd.install()
                }
            }
        }
    }
}
