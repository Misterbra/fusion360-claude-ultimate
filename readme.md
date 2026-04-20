# Fusion 360 MCP Server

A Model Context Protocol (MCP) server that enables Claude Desktop to control Autodesk Fusion 360 through natural language commands. Create, manipulate, and query 3D objects in Fusion 360 by simply describing what you want to do.

> **Inspiration:** This project is inspired by and adapted from the work of [Kanbara Tomonori](https://note.com/tomo1230ee), Autodesk certified Fusion 360 Expert Elite. This version provides a French-localized and extended implementation of the original MCP × Fusion API integration concept.

## Features

- **84+ CAD tools** accessible via natural language through Claude Desktop
- **Works on existing designs**: open any Fusion 360 file and Claude can inspect, modify, and extend it
- **Shape creation**: cubes, cylinders, boxes, spheres, hemispheres, cones, torus, pipes, polygon prisms, swept profiles
- **Sketch system**: create sketches with lines, circles, arcs, rectangles, polygons, splines, and text
- **Advanced modeling**: revolve, loft, sweep, construction planes
- **Patterns**: circular and rectangular arrays, symmetric copies, body duplication
- **Geometry operations**: shell, hole (counterbore/countersink), thread, draft, offset face, split body, scale
- **Boolean operations**: join, cut, intersect on selected or named bodies
- **Edge modifications**: fillets and chamfers with edge index selection
- **Transformations**: move and rotate bodies by name with full XYZ control
- **Materials & appearance**: assign physical materials and visual appearances
- **Export**: STL (3D printing), STEP (CAD interop), F3D (Fusion archive)
- **Parametric design**: create and modify named parameters
- **Query tools**: bounding box, dimensions, center of mass, mass properties, edge/face info, distance measurement
- **Viewport capture**: screenshot the viewport for AI visual feedback
- **Macro execution**: batch multiple commands in a single call
- **Real-time integration**: commands execute immediately in Fusion 360

## Prerequisites

- **Node.js** (version 14 or higher)
- **Autodesk Fusion 360** (installed and licensed)
- **Claude Desktop** application
- **Windows** or **macOS**

## Architecture

```
Claude Desktop  ──>  MCP Server (Node.js)  ──>  fusion_command.txt
                                                       │
Claude Desktop  <──  MCP Server (Node.js)  <──  fusion_response.txt
                                                       │
                                              Fusion 360 Add-in (Python)
                                                       │
                                              Fusion 360 Application
```

The MCP server communicates with Fusion 360 through JSON files (`~/Documents/fusion_command.txt` and `~/Documents/fusion_response.txt`). The Fusion 360 add-in polls for new commands every 0.5s and writes responses back.

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/fusion-claude-ultimate.git
cd fusion-claude-ultimate
```

### 2. Install dependencies

```bash
cd server
npm install
```

### 3. Install the Fusion 360 add-in

Copy the `fusion_script/fusion_mcp_server/` folder to your Fusion 360 add-ins directory:

**Windows:**
```
%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\
```

**macOS:**
```
~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/
```

Then in Fusion 360, go to **Tools > Add-Ins** and enable **Fusion MCP Server**.

### 4. Configure Claude Desktop

Edit your Claude Desktop configuration file:

**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`

Add the following (replace `YOUR_PATH` with the actual path to the project):

```json
{
  "mcpServers": {
    "fusion_mcp": {
      "command": "node",
      "args": ["YOUR_PATH/fusion-claude-ultimate/server/server.mjs"],
      "protocol": "stdio",
      "description": "Control Fusion 360 via MCP"
    }
  }
}
```

### 5. Restart Claude Desktop

Close Claude Desktop completely and restart it to load the new MCP server.

## Usage

Once configured, control Fusion 360 through natural language in Claude Desktop:

```
Create a cube with 50mm sides
Make a cylinder with radius 25mm and height 100mm
Create a torus with major radius 30mm and minor radius 10mm
Move "Cube1" 20mm along the X axis
Add a 3mm fillet to edges 0 and 1 of "Box1"
Combine "Cube1" and "Cylinder1" with a cut operation
What are the dimensions of "Box1"?
Shell "Box1" with 2mm wall thickness, removing the top face
Create a sketch on the XY plane, draw a circle, then extrude it 20mm
Make a vase shape: draw a profile and revolve it 360 degrees
Export the design as STL for 3D printing
Set the material to Aluminum on "Body1"
Capture a screenshot of the viewport
```

## Available Tools

### Shape Creation
| Tool | Description |
|------|-------------|
| `create_cube` | Create a cube with specified side length |
| `create_box` | Create a rectangular box (width, depth, height) |
| `create_cylinder` | Create a cylinder (radius, height) |
| `create_sphere` | Create a sphere (radius) |
| `create_hemisphere` | Create a hemisphere (radius) |
| `create_cone` | Create a cone (base radius, height, optional top radius) |
| `create_torus` | Create a torus (major/minor radius) |
| `create_half_torus` | Create a half torus |
| `create_pipe` | Create a pipe between two 3D points |
| `create_polygon_prism` | Create a polygon prism (N sides, radius, height) |
| `create_polygon_sweep` | Create a swept polygon profile along a path |

### Patterns & Copies
| Tool | Description |
|------|-------------|
| `copy_body_symmetric` | Create a mirror copy of a body |
| `copy_body` | Duplicate a body with optional offset |
| `create_circular_pattern` | Create a circular array of a body |
| `create_rectangular_pattern` | Create a rectangular grid array |

### Geometry Operations
| Tool | Description |
|------|-------------|
| `shell_body` | Hollow out a body with specified wall thickness |
| `create_hole` | Create simple or through-all holes |
| `create_counterbore_hole` | Stepped hole for socket head cap screws |
| `create_countersink_hole` | Tapered hole for flat head screws |
| `create_thread` | Add ISO metric threads to cylindrical faces |
| `create_tube` | Create a hollow tube/pipe (no boolean needed) |
| `offset_face` | Move faces inward/outward |
| `split_body` | Split a body with a construction plane |
| `scale_body` | Scale a body uniformly or non-uniformly |
| `draft_face` | Add draft angles to faces for mold release |
| `add_fillet` | Add rounded edges (by edge indices) |
| `add_chamfer` | Add beveled edges (by edge indices) |
| `combine_selection` | Boolean operation on two selected bodies |
| `combine_selection_all` | Boolean operation on all selected bodies |
| `combine_by_name` | Boolean operation on bodies by name |

### Sketch System
| Tool | Description |
|------|-------------|
| `sketch_create` | Create a new sketch on a plane or body face |
| `sketch_add_line` | Add a line to a sketch |
| `sketch_add_circle` | Add a circle to a sketch |
| `sketch_add_arc` | Add an arc through 3 points |
| `sketch_add_rectangle` | Add a rectangle to a sketch |
| `sketch_add_polygon` | Add a regular polygon to a sketch |
| `sketch_add_spline` | Add a fitted spline through points |
| `sketch_add_text` | Add text for embossing/debossing |
| `sketch_mirror` | Mirror sketch geometry across an axis |
| `sketch_offset` | Offset curves for parallel geometry (walls) |
| `sketch_fillet` | Round corners between two sketch curves |
| `sketch_extrude` | Extrude a profile (one-sided, negative, or symmetric) |

### Advanced Modeling
| Tool | Description |
|------|-------------|
| `create_revolve` | Revolve a sketch profile around an axis |
| `create_loft` | Smooth transition between 2+ sketch profiles |
| `create_sweep` | Sweep a profile along a path |
| `create_construction_plane` | Create an offset construction plane |
| `extrude_to_object` | Extrude until it reaches another body's surface |

### Assembly
| Tool | Description |
|------|-------------|
| `create_component` | Group bodies into a component/sub-assembly |

### Transformations & Visibility
| Tool | Description |
|------|-------------|
| `move_by_name` | Move a body by X/Y/Z offsets |
| `rotate_by_name` | Rotate a body around an axis |
| `hide_body` | Hide a body by name |
| `show_body` | Show a hidden body by name |

### Selection
| Tool | Description |
|------|-------------|
| `select_body` | Select a single body by name |
| `select_bodies` | Select two bodies by name |
| `select_all_bodies` | Select all bodies in the document |

### Query & Measurement
| Tool | Description |
|------|-------------|
| `get_bounding_box` | Get min/max coordinates of a body |
| `get_body_center` | Get the center point of a body |
| `get_body_dimensions` | Get width, depth, height of a body |
| `get_faces_info` | List all faces with indices and areas |
| `get_edges_info` | List all edges with indices and lengths |
| `get_mass_properties` | Get mass, volume, surface area, density |
| `get_body_relationships` | Get spatial relationship between two bodies |
| `measure_distance` | Measure distance between two bodies |
| `list_bodies` | List all bodies with names, sizes, and properties |

### Export
| Tool | Description |
|------|-------------|
| `export_stl` | Export as STL for 3D printing |
| `export_step` | Export as STEP for CAD interoperability |
| `export_f3d` | Export as Fusion 360 archive |

### Materials & Appearance
| Tool | Description |
|------|-------------|
| `set_material` | Assign physical material (steel, aluminum, ABS...) |
| `set_appearance` | Assign visual appearance |

### Parametric Design
| Tool | Description |
|------|-------------|
| `set_user_parameter` | Create or update a named parameter |
| `get_user_parameter` | Read parameter values |

### Design Inspection (work on existing files)
| Tool | Description |
|------|-------------|
| `get_design_info` | Get document name, units, body/feature/component counts |
| `list_bodies` | List all bodies with names, sizes, and properties |
| `list_features` | List all features in the timeline with types |
| `list_sketches` | List all sketches with profile/curve counts |
| `list_components` | List all components and occurrences |
| `rename_body` | Rename an existing body |
| `suppress_feature` | Suppress a feature (non-destructive disable) |
| `unsuppress_feature` | Re-enable a suppressed feature |
| `delete_feature` | Delete a specific feature from the timeline |

### Utility
| Tool | Description |
|------|-------------|
| `execute_macro` | Execute multiple commands in sequence |
| `delete_all_features` | Clear all features from the design |
| `capture_viewport` | Screenshot the viewport as PNG |
| `debug_coordinate_info` | Output coordinate system debug info |

## Project Structure

```
fusion-claude-ultimate/
├── server/
│   ├── server.mjs                 # MCP server (Node.js)
│   ├── package.json               # Dependencies
│   └── mcp_server.log             # Runtime logs
├── fusion_script/
│   └── fusion_mcp_server/
│       ├── fusion_mcp_server.py   # Fusion 360 add-in (Python)
│       └── fusion_mcp_server.manifest
├── AppDataRoamingClaude/
│   └── claude_desktop_config.json # Example configuration
└── readme.md
```

## Troubleshooting

### Check server logs
```bash
# Real-time logs (macOS/Linux)
tail -f server/mcp_server.log

# Windows
type server\mcp_server.log
```

### Verify commands are being sent
```bash
# Windows
type "%USERPROFILE%\Documents\fusion_command.txt"

# macOS/Linux
cat ~/Documents/fusion_command.txt
```

### Common issues

| Problem | Solution |
|---------|----------|
| Claude Desktop doesn't detect the server | Restart Claude Desktop after config changes |
| Commands not reaching Fusion 360 | Check that the add-in is running (Tools > Add-Ins) |
| Permission errors | Ensure write access to `~/Documents/` |
| Node.js not found | Verify `node` is in your PATH |
| Timeout errors | Check that Fusion 360 is open and the add-in is started |

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Disclaimer

This software is provided as-is. Use at your own risk. Save your Fusion 360 work before using this tool.

## Acknowledgments

- **Original concept**: [Kanbara Tomonori](https://note.com/tomo1230ee) — Autodesk certified Fusion 360 Expert Elite
- [Model Context Protocol (MCP)](https://github.com/modelcontextprotocol) by Anthropic
- [Fusion 360](https://www.autodesk.com/products/fusion-360) by Autodesk
- [Claude Desktop](https://claude.ai/download) by Anthropic
