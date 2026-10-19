fn main() {
    let path = concat!(env!("CARGO_MANIFEST_DIR"), "/../schema/scene.schema.json");
    std::fs::write(path, sp_core::scene::scene_json_schema()).expect("write scene schema");
    println!("wrote {path}");
}
