# Fusion 360 MCP Server

A Model Context Protocol (MCP) server that enables Claude Desktop to control Fusion 360 through natural language commands. Create, manipulate, and modify 3D objects in Fusion 360 by simply describing what you want to do.

> **Inspiration:** This project is inspired by and adapted from the excellent work by [神原 友徳 (Kanbara Tomonori)](https://note.com/tomo1230/n/n123abc), an Autodesk certified Fusion 360 Expert Elite. This version provides a French-localized and slightly modified implementation of the original MCP × Fusion API integration concept.

## 📝 About This Implementation

This project is a French-localized adaptation of the original Japanese tutorial by Kanbara Tomonori. Key modifications include:

- **Language Localization**: Server comments and messages in French
- **Simplified Architecture**: Streamlined command structure for easier understanding
- **Enhanced Documentation**: Comprehensive English documentation for international users
- **Cross-platform Support**: Updated configuration for Windows, macOS, and Linux

The core functionality and API design remain faithful to the original concept while making it more accessible to French-speaking developers and the international community.

### Check Server Logs
The server creates a log file in the server directory:
```bash
# View real-time logs
tail -f server/mcp_server.log

# On Windows
type server\mcp_server.log
```

### Verify Command File
Check if commands are being written:
```bash
# Windows
type "%USERPROFILE%\Documents\fusion_command.txt"

# macOS/Linux
cat ~/Documents/fusion_command.txt
```

### Common Issues

1. **Path Issues**: Make sure the path in your configuration matches your actual project location
2. **Node.js Not Found**: Ensure Node.js is installed and accessible from command line
3. **Permission Errors**: Check that the script has write permissions to the Documents folder
4. **Claude Desktop Not Detecting Server**: Restart Claude Desktop after configuration changes

### Testing the Server
You can test the server manually:
```bash
cd server
node server.js
```

The server should show "🚀 Serveur MCP Fusion démarré - Compatible version HYBRIDE" and wait for input.

## 🔍 Troubleshooting

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## ⚠️ Disclaimer

This software is provided as-is. Use at your own risk. Make sure to save your Fusion 360 work before using this tool.

## 🙏 Acknowledgments

- **Original Concept**: [神原 友徳 (Kanbara Tomonori)](https://note.com/tomo1230/) - Autodesk certified Fusion 360 Expert Elite
- **Original Tutorial**: ["🧠 Claude AIとAutodesk Fusion をつなぐ！「MCP × Fusion API」連携チュートリアル"](https://note.com/tomo1230/n/n123abc)
- [Model Context Protocol (MCP)](https://github.com/modelcontextprotocol) by Anthropic
- [Fusion 360](https://www.autodesk.com/products/fusion-360) by Autodesk
- [Claude Desktop](https://claude.ai/download) by Anthropic

## 📚 Related Resources

- [Original Japanese Implementation](https://note.com/tomo1230/) by Kanbara Tomonori
- [MCP Documentation](https://docs.anthropic.com/en/docs/build-with-claude/mcp)
- [Fusion 360 API Documentation](https://help.autodesk.com/view/fusion360/ENU/?guid=GUID-A92A4B10-3781-4925-94C6-47DA85A4F65A) 🚀 Features

- **Shape Creation**: Create cubes, cylinders, boxes, spheres, cones, and pyramids
- **Object Manipulation**: Move, rotate, and combine objects
- **Advanced Operations**: Add fillets, select edges, and perform boolean operations
- **Natural Language Interface**: Control Fusion 360 through conversational commands
- **Real-time Integration**: Commands are executed immediately in Fusion 360

## 📋 Prerequisites

- **Node.js** (version 14 or higher)
- **Fusion 360** (installed and licensed)
- **Claude Desktop** application
- **Windows, macOS, or Linux**

## 🔧 Installation

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/fusion-claude-ultimate.git
cd fusion-claude-ultimate
```

### 2. Navigate to Server Directory

```bash
cd fusion-claude-ultimate/server
npm init -y
```

### 3. Configure Claude Desktop

You can use the included `claude_desktop_config.json` file or manually edit your Claude Desktop configuration:

**Option A: Use the included config file**
Copy the `claude_desktop_config.json` from this repository to your Claude Desktop configuration directory:

**Windows:**
```bash
copy claude_desktop_config.json %APPDATA%\Claude\claude_desktop_config.json
```

**macOS:**
```bash
cp claude_desktop_config.json ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

**Linux:**
```bash
cp claude_desktop_config.json ~/.config/Claude/claude_desktop_config.json
```

**Option B: Manual configuration**
Edit your Claude Desktop configuration file and add this configuration (replace `YOUR_USERNAME` with your actual username):

```json
{
  "mcpServers": {
    "fusion_mcp": {
      "command": "node",
      "args": ["C:\\Users\\YOUR_USERNAME\\Desktop\\fusion-claude-ultimate\\server\\server.js"],
      "protocol": "stdio",
      "description": "Control Fusion 360 via MCP"
    }
  }
}
```

**For macOS/Linux, use forward slashes:**
```json
{
  "mcpServers": {
    "fusion_mcp": {
      "command": "node",
      "args": ["/Users/YOUR_USERNAME/Desktop/fusion-claude-ultimate/server/server.js"],
      "protocol": "stdio",
      "description": "Control Fusion 360 via MCP"
    }
  }
}
```

### 4. Restart Claude Desktop

Close Claude Desktop completely and restart it to load the new MCP server.

## 🎯 Usage

Once configured, you can control Fusion 360 through natural language in Claude Desktop:

### Shape Creation Examples

```
Create a cube with 50mm sides
Make a cylinder with radius 25mm and height 100mm
Create a box 80mm wide, 60mm deep, and 40mm tall
Generate a sphere with 30mm radius
Make a cone with base radius 20mm and height 50mm
Create a square pyramid with 40mm base and 60mm height
```

### Manipulation Examples

```
Move the selection 10mm in X direction
Rotate the selected object 45 degrees around Z axis
Combine the two selected objects using join operation
Add a 5mm fillet to all edges
Select the object named "Cylinder1"
```

## 🛠️ Available Commands

### Creation Tools
- `create_cube` - Create cubic shapes
- `create_cylinder` - Create cylindrical shapes
- `create_box` - Create rectangular boxes
- `create_sphere` - Create spherical shapes
- `create_cone` - Create conical shapes
- `create_sq_pyramid` - Create square pyramids
- `create_tri_pyramid` - Create triangular pyramids

### Manipulation Tools
- `move_selection` - Move selected objects
- `rotate_selection` - Rotate selected objects
- `combine_selection` - Combine two selected objects
- `combine_by_name` - Combine objects by their names

### Selection Tools
- `select_body` - Select an object by name
- `select_bodies` - Select multiple objects
- `select_edges` - Select edges of an object

### Modification Tools
- `add_fillet` - Add rounded edges
- `undo` - Undo last operation
- `redo` - Redo last undone operation

## 📂 Project Structure

```
fusion-claude-ultimate/
│
├── .git/                           # Git repository data
├── AppDataRoamingClaude/          # Claude configuration files
├── fusion_script/                 # Fusion 360 Python scripts
├── server/
│   └── server.js                  # Main MCP server
├── claude_desktop_config.json    # Claude Desktop configuration
└── README.md                     # This file
```

##