import QtQuick

// Right dock for Mesh Lods, Texture Params, Texture Editor, Texture Denoiser.
// Maps preview stays a widget in the well under the tabs.
Item {
    id: dock

    readonly property color ink: bridge.dark ? "#f2f4f8" : "#1d1d1f"
    readonly property color mute: bridge.dark ? "#8b93a1" : "#5c6570"
    property real padTop: 16 + headCol.height + 8

    function blocks() {
        try { return JSON.parse(bridge.formBlocks) }
        catch (e) { return [] }
    }
    function tabs() {
        try { return JSON.parse(bridge.formTabs) }
        catch (e) { return [] }
    }

    GlassPlate {
        anchors.fill: parent
        visible: dock.width > 40
        dark: bridge.dark
        plateRadius: 16
        foot: 8

        Item {
            anchors.fill: parent

            Column {
                id: headCol
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.right: parent.right
                spacing: 8

                Text {
                    width: parent.width
                    text: (typeof bridge.formTitle === "string" ? qsTr(bridge.formTitle) : bridge.formTitle)
                    color: dock.ink
                    font.pixelSize: 15
                    font.bold: true
                    elide: Text.ElideRight
                }

                Item {
                    id: tabStrip
                    visible: dock.tabs().length > 1
                    width: parent.width
                    height: visible ? 36 : 0

                    Rectangle {
                        anchors.fill: parent
                        radius: 12
                        color: Qt.rgba(0, 0, 0, bridge.dark ? 0.32 : 0.06)
                        border.width: 1
                        border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.40)
                    }
                    Item {
                        id: tabPill
                        z: 1
                        y: 3
                        height: 30
                        visible: tabStrip.visible && dock.tabs().length > 0
                        width: visible ? (tabStrip.width - 6) / dock.tabs().length : 0
                        x: 3 + bridge.formTab * width
                        Behavior on x { NumberAnimation { duration: 280; easing.type: Easing.OutCubic } }

                        Repeater {
                            model: 3
                            delegate: Rectangle {
                                required property int index
                                property real t: (index + 1) / 3
                                anchors.fill: parent
                                anchors.leftMargin: 1 - t * 2
                                anchors.rightMargin: 1 - t * 2
                                anchors.topMargin: 1 + index
                                anchors.bottomMargin: -t * 2
                                radius: 10
                                color: Qt.rgba(0, 0, 0, 0.22 * (1.05 - t))
                            }
                        }
                        Rectangle {
                            anchors.fill: parent
                            anchors.bottomMargin: 2
                            radius: 10
                            gradient: Gradient {
                                GradientStop { position: 0.0; color: "#ff7a45" }
                                GradientStop { position: 0.42; color: "#ff5a1f" }
                                GradientStop { position: 1.0; color: "#c43a10" }
                            }
                            Rectangle {
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.leftMargin: 10
                                anchors.rightMargin: 10
                                anchors.topMargin: 1
                                height: 1
                                color: Qt.rgba(1, 1, 1, 0.55)
                            }
                        }
                    }
                    Row {
                        z: 2
                        anchors.fill: parent
                        Repeater {
                            model: dock.tabs()
                            delegate: Item {
                                required property string modelData
                                required property int index
                                width: tabStrip.width / dock.tabs().length
                                height: tabStrip.height
                                Text {
                                    anchors.centerIn: parent
                                    text: (typeof modelData === "string" ? qsTr(modelData) : modelData)
                                    color: index === bridge.formTab ? "#ffffff" : dock.ink
                                    font.pixelSize: 12
                                    font.bold: index === bridge.formTab
                                }
                                TapHandler { onTapped: bridge.setFormTab(index) }
                            }
                        }
                    }
                }
            }

            Flickable {
                anchors.top: headCol.bottom
                anchors.topMargin: 10
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                visible: !bridge.formTool
                clip: true
                contentHeight: formCol.height
                boundsBehavior: Flickable.StopAtBounds

                Column {
                    id: formCol
                    width: parent.width
                    spacing: 8

                    Repeater {
                        model: dock.blocks()
                        delegate: Item {
                            required property var modelData
                            width: formCol.width
                            height: {
                                if (modelData.type === "section" || modelData.type === "note")
                                    return Math.max(18, noteText.implicitHeight)
                                if (modelData.type === "pills")
                                    return 58
                                if (modelData.type === "buttons" || modelData.type === "file")
                                    return 40
                                if (modelData.type === "check")
                                    return 28
                                return 36
                            }

                            Text {
                                id: noteText
                                visible: modelData.type === "note" || modelData.type === "section"
                                width: parent.width
                                wrapMode: Text.WordWrap
                                text: modelData.type === "section" ? modelData.label : (modelData.text || "")
                                color: modelData.type === "section" ? dock.ink : dock.mute
                                font.pixelSize: modelData.type === "section" ? 11 : 12
                                font.bold: modelData.type === "section"
                                font.capitalization: modelData.type === "section" ? Font.AllUppercase : Font.MixedCase
                            }

                            SunkField {
                                visible: modelData.type === "field"
                                anchors.left: parent.left
                                anchors.right: parent.right
                                label: modelData.label || ""
                                value: modelData.value || ""
                                fieldEnabled: modelData.enabled !== false
                                onEdited: bridge.setDockField(modelData.id, text)
                            }

                            Row {
                                visible: modelData.type === "file"
                                width: parent.width
                                spacing: 6
                                SunkField {
                                    width: parent.width - 42
                                    label: modelData.label || ""
                                    value: modelData.value || ""
                                    fieldEnabled: modelData.enabled !== false
                                    hasCheck: !!modelData.check
                                    checked: !!modelData.on
                                    onEdited: bridge.setDockField(modelData.id, text)
                                    onToggled: bridge.setDockField(modelData.check, modelData.on ? "0" : "1")
                                }
                                RaiseButton {
                                    width: 36
                                    height: 36
                                    glyph: modelData.glyph || ""
                                    fontName: bridge.iconFont
                                    tip: qsTr("Choose file")
                                    enabled: modelData.enabled !== false
                                    opacity: enabled ? 1 : 0.4
                                    onClicked: bridge.runDock(modelData.pick)
                                }
                            }

                            Column {
                                visible: modelData.type === "pills"
                                width: parent.width
                                spacing: 4
                                Text {
                                    text: modelData.label || ""
                                    color: dock.mute
                                    font.pixelSize: 11
                                }
                                Item {
                                    id: pills
                                    width: parent.width
                                    height: 34
                                    opacity: modelData.enabled === false ? 0.4 : 1
                                    property var opts: modelData.options || []
                                    property string fid: modelData.id || ""
                                    property string current: modelData.value || ""
                                    property bool live: modelData.enabled !== false
                                    Rectangle {
                                        anchors.fill: parent
                                        radius: 10
                                        color: Qt.rgba(0, 0, 0, bridge.dark ? 0.32 : 0.06)
                                    }
                                    Row {
                                        anchors.fill: parent
                                        Repeater {
                                            model: pills.opts
                                            delegate: Item {
                                                required property string modelData
                                                required property int index
                                                width: pills.opts.length > 0 ? pills.width / pills.opts.length : 0
                                                height: pills.height
                                                Item {
                                                    anchors.fill: parent
                                                    anchors.margins: 3
                                                    visible: modelData === pills.current
                                                    Repeater {
                                                        model: 3
                                                        delegate: Rectangle {
                                                            required property int index
                                                            property real t: (index + 1) / 3
                                                            anchors.fill: parent
                                                            anchors.leftMargin: 1 - t * 2
                                                            anchors.rightMargin: 1 - t * 2
                                                            anchors.topMargin: 1 + index
                                                            anchors.bottomMargin: -t * 2
                                                            radius: 8
                                                            color: Qt.rgba(0, 0, 0, 0.22 * (1.05 - t))
                                                        }
                                                    }
                                                    Rectangle {
                                                        anchors.fill: parent
                                                        anchors.bottomMargin: 2
                                                        radius: 8
                                                        gradient: Gradient {
                                                            GradientStop { position: 0.0; color: "#ff7a45" }
                                                            GradientStop { position: 0.42; color: "#ff5a1f" }
                                                            GradientStop { position: 1.0; color: "#c43a10" }
                                                        }
                                                        Rectangle {
                                                            anchors.left: parent.left
                                                            anchors.right: parent.right
                                                            anchors.top: parent.top
                                                            anchors.leftMargin: 8
                                                            anchors.rightMargin: 8
                                                            anchors.topMargin: 1
                                                            height: 1
                                                            color: Qt.rgba(1, 1, 1, 0.55)
                                                        }
                                                    }
                                                }
                                                Text {
                                                    anchors.centerIn: parent
                                                    text: (typeof modelData === "string" ? qsTr(modelData) : modelData)
                                                    color: modelData === pills.current ? "#ffffff" : dock.ink
                                                    font.pixelSize: 11
                                                    font.bold: modelData === pills.current
                                                }
                                                TapHandler {
                                                    onTapped: if (pills.live)
                                                        bridge.setDockField(pills.fid, modelData)
                                                }
                                            }
                                        }
                                    }
                                }
                            }

                            Row {
                                visible: modelData.type === "check"
                                spacing: 8
                                width: parent.width
                                Rectangle {
                                    width: 18
                                    height: 18
                                    radius: 5
                                    anchors.verticalCenter: parent.verticalCenter
                                    color: modelData.on ? "#ff5a1f" : Qt.rgba(0, 0, 0, bridge.dark ? 0.35 : 0.08)
                                    border.width: 1
                                    border.color: Qt.rgba(1, 1, 1, 0.2)
                                    Text {
                                        anchors.centerIn: parent
                                        visible: modelData.on
                                        text: qsTr("✓")
                                        color: "#ffffff"
                                        font.pixelSize: 12
                                    }
                                }
                                Text {
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: parent.width - 26
                                    text: modelData.label || ""
                                    color: modelData.enabled === false ? dock.mute : dock.ink
                                    font.pixelSize: 12
                                    elide: Text.ElideRight
                                }
                                TapHandler {
                                    onTapped: if (modelData.enabled !== false)
                                        bridge.setDockField(modelData.id, modelData.on ? "0" : "1")
                                }
                            }

                            Row {
                                id: btnRow
                                visible: modelData.type === "buttons"
                                width: parent.width
                                spacing: 6
                                property var items: modelData.items || []
                                Repeater {
                                    model: btnRow.items
                                    delegate: RaiseButton {
                                        required property var modelData
                                        required property int index
                                        width: btnRow.items.length > 0
                                               ? (btnRow.width - 6 * (btnRow.items.length - 1)) / btnRow.items.length
                                               : btnRow.width
                                        height: 36
                                        label: modelData.label || ""
                                        glyph: modelData.glyph || ""
                                        tip: modelData.label || ""
                                        fontName: bridge.iconFont
                                        accent: !!modelData.accent
                                        onClicked: bridge.runDock(modelData.id)
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
