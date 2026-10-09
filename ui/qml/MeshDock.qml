import QtQuick

// Right Editor dock. Fields write back into the hidden editor widgets.
// Chrome matches Engine Tuner Auto Tune: title, cards, sunk fields, raised actions.
Item {
    id: dock

    readonly property var bag: {
        try { return JSON.parse(bridge.dockJson) } catch (e) { return {} }
    }
    readonly property var mat: bag.mat || {}
    readonly property var att: bag.att || {}
    readonly property color ink: bridge.dark ? "#f2f4f8" : "#1d1d1f"
    readonly property color mute: bridge.dark ? "#8b93a1" : "#5c6570"
    readonly property color line: Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.40)
    readonly property color well: Qt.rgba(0, 0, 0, bridge.dark ? 0.28 : 0.05)

    FontLoader { id: mi; source: bridge.iconFontUrl }

    Column {
        id: head
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        spacing: 4
        Text {
            text: dock.bag.title || qsTr("Editor")
            color: dock.ink
            font.pixelSize: 15
            font.bold: true
        }
        Text {
            text: dock.bag.sub || ""
            color: dock.mute
            font.pixelSize: 11
            width: parent.width
            wrapMode: Text.Wrap
            visible: text.length > 0
        }
        Text {
            visible: (dock.bag.tip || "").length > 0
            text: dock.bag.tip || ""
            color: dock.mute
            font.pixelSize: 11
            width: parent.width
            wrapMode: Text.Wrap
        }
    }

    Flickable {
        anchors.top: head.bottom
        anchors.topMargin: 10
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: foot.top
        anchors.bottomMargin: 10
        contentWidth: width
        contentHeight: form.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds

        Column {
            id: form
            width: parent.width
            spacing: 10

            Column {
                width: parent.width
                spacing: 10
                visible: dock.bag.mode === "meshes"
                Card {
                    title: ""
                    Field { label: "Name"; live: dock.mat.name || ""; onCommit: function (t) { bridge.setText("matName", t) } }
                    Text { text: "Type"; color: dock.mute; font.pixelSize: 11 }
                    Flow {
                        width: parent.width
                        spacing: 6
                        Repeater {
                            model: dock.mat.types || []
                            delegate: Chip {
                                required property string modelData
                                required property int index
                                label: (typeof modelData === "string" ? qsTr(modelData) : modelData)
                                on: index === dock.mat.type
                                onPicked: bridge.setCombo("type", index)
                            }
                        }
                    }
                    CheckRow {
                        label: qsTr("Double Sided")
                        checked: dock.mat.two === true
                        onToggled: bridge.setChecked("two", !dock.mat.two)
                    }
                    Field { label: "Vertices"; live: dock.mat.vfmt || "—"; lock: true; onCommit: function (t) {} }
                }
                Card {
                    title: qsTr("Textures")
                    Row {
                        width: parent.width
                        height: 16
                        Text { width: 88; text: "Map"; color: dock.mute; font.pixelSize: 11 }
                        Text { text: "File"; color: dock.mute; font.pixelSize: 11 }
                    }
                    Repeater {
                        model: dock.mat.tex || []
                        delegate: Item {
                            required property var modelData
                            width: parent.width
                            height: 48
                            Field {
                                width: parent.width - 28
                                label: (typeof modelData.k === "string" ? qsTr(modelData.k) : modelData.k)
                                live: modelData.v || ""
                                onCommit: function (t) { bridge.setText("tex:" + modelData.k, t) }
                            }
                            Text {
                                x: parent.width - 16
                                y: 26
                                text: modelData.lock ? "\ue897" : bridge.folderGlyph
                                font.family: mi.name.length > 0 ? mi.name : bridge.iconFont
                                color: dock.mute
                                font.pixelSize: 16
                                opacity: modelData.lock ? 0.4 : 1
                                HoverHandler { enabled: !modelData.lock; cursorShape: Qt.PointingHandCursor }
                                TapHandler { onTapped: if (!modelData.lock) bridge.clickId("texBrowse:" + modelData.k) }
                            }
                        }
                    }
                }
                Card {
                    title: qsTr("Color")
                    Rgba { which: "color"; title: "Material Color"; ch: dock.mat.color || [0, 0, 0, 255]; pick: "color" }
                    Rgba { which: "emis"; title: "matEmissive"; ch: dock.mat.emis || [0, 0, 0, 255]; pick: "emisPick" }
                    Rgba { which: "spec"; title: "matSpecular"; ch: dock.mat.specC || [0, 0, 0, 255]; pick: "specPick" }
                    Field { label: "specPower"; live: String(dock.mat.spec || 0); onCommit: function (t) { bridge.setSpin("spec", Number(t)) } }
                }
            }

            Column {
                width: parent.width
                spacing: 10
                visible: dock.bag.mode === "attachs"
                Card {
                    title: qsTr("Attachment")
                    Field { label: "Name"; live: dock.att.name || ""; onCommit: function (t) { bridge.setText("attName", t) } }
                    Field { label: "Parent"; live: dock.att.parent || ""; onCommit: function (t) { bridge.setText("attParent", t) } }
                }
                Card {
                    title: qsTr("Location")
                    Grid {
                        width: parent.width
                        columns: 3
                        columnSpacing: 6
                        rowSpacing: 6
                        Field { width: (parent.width - 12) / 3; label: "X"; live: String((dock.att.loc || [0, 0, 0])[0]); onCommit: function (t) { bridge.setSpin("loc0", Number(t)) } }
                        Field { width: (parent.width - 12) / 3; label: "Y"; live: String((dock.att.loc || [0, 0, 0])[1]); onCommit: function (t) { bridge.setSpin("loc1", Number(t)) } }
                        Field { width: (parent.width - 12) / 3; label: "Z"; live: String((dock.att.loc || [0, 0, 0])[2]); onCommit: function (t) { bridge.setSpin("loc2", Number(t)) } }
                    }
                }
                Card {
                    title: qsTr("Rotation")
                    Grid {
                        width: parent.width
                        columns: 2
                        columnSpacing: 6
                        rowSpacing: 6
                        Field { width: (parent.width - 6) / 2; label: "X"; live: String((dock.att.rot || [0, 0, 0, 1])[0]); onCommit: function (t) { bridge.setSpin("rot0", Number(t)) } }
                        Field { width: (parent.width - 6) / 2; label: "Y"; live: String((dock.att.rot || [0, 0, 0, 1])[1]); onCommit: function (t) { bridge.setSpin("rot1", Number(t)) } }
                        Field { width: (parent.width - 6) / 2; label: "Z"; live: String((dock.att.rot || [0, 0, 0, 1])[2]); onCommit: function (t) { bridge.setSpin("rot2", Number(t)) } }
                        Field { width: (parent.width - 6) / 2; label: "W"; live: String((dock.att.rot || [0, 0, 0, 1])[3]); onCommit: function (t) { bridge.setSpin("rot3", Number(t)) } }
                    }
                }
            }
        }
    }

    Column {
        id: foot
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        spacing: 6
        Rectangle {
            width: parent.width
            height: 1
            color: dock.line
        }
        Row {
            width: parent.width
            spacing: 6
            visible: dock.bag.mode === "attachs"
            RaiseButton {
                width: (parent.width - 12) / 3
                height: 34
                label: qsTr("Apply")
                accent: true
                enabled: dock.bag.applyOn === true
                onClicked: bridge.clickId("apply")
            }
            RaiseButton {
                width: (parent.width - 12) / 3
                height: 34
                label: qsTr("Add")
                enabled: dock.bag.addOn === true
                onClicked: bridge.clickId("add")
            }
            RaiseButton {
                width: (parent.width - 12) / 3
                height: 34
                label: qsTr("Delete")
                enabled: dock.bag.delOn === true
                onClicked: bridge.clickId("del")
            }
        }
        Text {
            text: qsTr("File")
            color: dock.mute
            font.pixelSize: 11
        }
        Row {
            spacing: 8
            RaiseButton {
                width: 36
                height: 36
                accent: true
                enabled: dock.bag.saveOn === true
                glyph: bridge.saveGlyph
                fontName: mi.name.length > 0 ? mi.name : bridge.iconFont
                tip: qsTr("Save")
                onClicked: bridge.clickId("save")
            }
            RaiseButton {
                width: 36
                height: 36
                enabled: dock.bag.saveOn === true
                glyph: bridge.saveGlyph
                fontName: mi.name.length > 0 ? mi.name : bridge.iconFont
                tip: qsTr("Save As")
                onClicked: bridge.clickId("saveAs")
            }
        }
    }

    component Card: Rectangle {
        property string title: ""
        default property alias body: inner.data
        width: parent ? parent.width : 0
        height: inner.height + 16
        radius: 12
        color: dock.well
        border.width: 1
        border.color: dock.line
        Column {
            id: inner
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.margins: 8
            spacing: 6
            Text {
                visible: title.length > 0
                text: (typeof title === "string" ? qsTr(title) : title)
                color: dock.ink
                font.pixelSize: 13
                font.bold: true
            }
        }
    }

    component CheckRow: Item {
        property string label: ""
        property bool checked: false
        signal toggled()
        width: parent ? parent.width : 0
        height: 22
        Rectangle {
            id: box
            width: 16
            height: 16
            anchors.verticalCenter: parent.verticalCenter
            radius: 4
            color: Qt.rgba(0, 0, 0, bridge.dark ? 0.40 : 0.08)
            border.width: 1
            border.color: checked ? "#ff5a1f" : dock.line
            Rectangle {
                anchors.centerIn: parent
                width: 8
                height: 8
                radius: 2
                color: checked ? "#ff5a1f" : "transparent"
            }
        }
        Text {
            anchors.left: box.right
            anchors.leftMargin: 8
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            text: (typeof parent.label === "string" ? qsTr(parent.label) : parent.label)
            color: dock.ink
            font.pixelSize: 12
            elide: Text.ElideRight
        }
        HoverHandler { cursorShape: Qt.PointingHandCursor }
        TapHandler { onTapped: parent.toggled() }
    }

    component Chip: Rectangle {
        property string label: ""
        property bool on: false
        signal picked()
        width: chipLab.implicitWidth + 16
        height: 28
        radius: 8
        color: on ? "#ff5a1f" : Qt.rgba(0, 0, 0, bridge.dark ? 0.35 : 0.06)
        border.width: on ? 0 : 1
        border.color: dock.line
        Text {
            id: chipLab
            anchors.centerIn: parent
            text: (typeof label === "string" ? qsTr(label) : label)
            color: on ? "#ffffff" : dock.ink
            font.pixelSize: 11
            font.bold: on
        }
        HoverHandler { cursorShape: Qt.PointingHandCursor }
        TapHandler { onTapped: picked() }
    }

    component Field: Item {
        property string label: ""
        property string live: ""
        property bool lock: false
        signal commit(string text)
        width: parent ? parent.width : 200
        height: label.length > 0 ? 48 : 32
        Text {
            id: lab
            visible: label.length > 0
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            height: visible ? 14 : 0
            text: (typeof label === "string" ? qsTr(label) : label)
            color: dock.mute
            font.pixelSize: 11
            elide: Text.ElideRight
        }
        Item {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: lab.bottom
            anchors.topMargin: lab.visible ? 2 : 0
            height: 32
            Rectangle {
                anchors.fill: parent
                radius: 8
                color: Qt.rgba(0, 0, 0, bridge.dark ? 0.50 : 0.10)
                border.width: 1
                border.color: Qt.rgba(0, 0, 0, bridge.dark ? 0.55 : 0.18)
            }
            Rectangle {
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.margins: 1
                height: 10
                radius: 8
                gradient: Gradient {
                    GradientStop { position: 0.0; color: Qt.rgba(0, 0, 0, bridge.dark ? 0.45 : 0.14) }
                    GradientStop { position: 1.0; color: Qt.rgba(0, 0, 0, 0) }
                }
            }
            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.leftMargin: 6
                anchors.rightMargin: 6
                height: 1
                color: Qt.rgba(1, 1, 1, bridge.dark ? 0.10 : 0.40)
            }
            TextInput {
                id: input
                anchors.fill: parent
                anchors.leftMargin: 8
                anchors.rightMargin: 8
                verticalAlignment: TextInput.AlignVCenter
                color: dock.ink
                font.pixelSize: 12
                selectByMouse: !lock
                readOnly: lock
                clip: true
                text: input.activeFocus ? input.text : live
                onEditingFinished: if (!lock) commit(text)
            }
        }
    }

    component Rgba: Column {
        property string which: ""
        property string title: ""
        property var ch: [0, 0, 0, 255]
        property string pick: ""
        width: parent.width
        spacing: 4
        Text { text: title; color: dock.mute; font.pixelSize: 11 }
        Row {
            spacing: 4
            Repeater {
                model: ["R", "G", "B", "A"]
                delegate: Item {
                    required property string modelData
                    required property int index
                    width: 46
                    height: 32
                    Text {
                        anchors.left: parent.left
                        anchors.verticalCenter: parent.verticalCenter
                        text: (typeof modelData === "string" ? qsTr(modelData) : modelData)
                        color: dock.mute
                        font.pixelSize: 10
                    }
                    Rectangle {
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        width: 34
                        height: 28
                        radius: 6
                        color: Qt.rgba(0, 0, 0, bridge.dark ? 0.50 : 0.10)
                        border.width: 1
                        border.color: Qt.rgba(0, 0, 0, bridge.dark ? 0.55 : 0.18)
                        Rectangle {
                            anchors.top: parent.top
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.margins: 1
                            height: 8
                            radius: 6
                            gradient: Gradient {
                                GradientStop { position: 0.0; color: Qt.rgba(0, 0, 0, bridge.dark ? 0.40 : 0.12) }
                                GradientStop { position: 1.0; color: Qt.rgba(0, 0, 0, 0) }
                            }
                        }
                        TextInput {
                            anchors.fill: parent
                            horizontalAlignment: TextInput.AlignHCenter
                            verticalAlignment: TextInput.AlignVCenter
                            color: dock.ink
                            font.pixelSize: 11
                            text: activeFocus ? text : String((ch && ch[index]) || 0)
                            validator: IntValidator { bottom: 0; top: 255 }
                            onEditingFinished: bridge.setChannel(which, index, Number(text))
                        }
                    }
                }
            }
            Rectangle {
                width: 28
                height: 28
                radius: 6
                anchors.verticalCenter: parent.verticalCenter
                color: Qt.rgba((ch[0] || 0) / 255, (ch[1] || 0) / 255, (ch[2] || 0) / 255, 1)
                border.width: 1
                border.color: dock.line
                HoverHandler { cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: bridge.clickId(pick) }
            }
        }
    }
}
